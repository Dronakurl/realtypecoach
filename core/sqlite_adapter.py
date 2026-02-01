"""SQLite adapter for RealTypeCoach database operations."""

import csv
import logging
import queue
import re
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

import sqlcipher3 as sqlite3

from core.database_adapter import AdapterError, ConnectionError, DatabaseAdapter
from core.models import (
    BurstTimeSeries,
    DailySummaryDB,
    DigraphPerformance,
    KeyPerformance,
    TypingTimeDataPoint,
    WordStatisticsLite,
)

log = logging.getLogger("realtypecoach.sqlite_adapter")


class _PooledConnection:
    """Wrapper for a pooled database connection with metadata."""

    def __init__(self, conn: sqlite3.Connection, created_at: float):
        self.conn = conn
        self.created_at = created_at
        self.in_use = False


class ConnectionPool:
    """Thread-safe connection pool for SQLCipher database connections.

    Reuses encrypted connections to avoid expensive encryption/decryption overhead.
    Connections are rotated after max_lifetime_sec to prevent staleness.
    """

    def __init__(
        self,
        db_path: Path,
        crypto,
        pool_size: int = 10,
        max_lifetime_sec: int = 300,
        acquire_timeout: float = 30.0,
    ):
        """Initialize connection pool.

        Args:
            db_path: Path to SQLite database file
            crypto: CryptoManager instance for key retrieval
            pool_size: Maximum number of connections to maintain
            max_lifetime_sec: Rotate connections after this many seconds
            acquire_timeout: Seconds to wait for connection acquisition
        """
        self._db_path = db_path
        self._crypto = crypto
        self._pool_size = pool_size
        self._max_lifetime = max_lifetime_sec
        self._acquire_timeout = acquire_timeout
        self._pool: queue.Queue[_PooledConnection] = queue.Queue(maxsize=pool_size)
        self._lock = threading.RLock()  # Use RLock for reentrancy (needed in _create_connection)
        self._created_connections = 0

    @contextmanager
    def get_connection(self):
        """Get a connection from the pool.

        Yields:
            sqlite3.Connection: A database connection

        Raises:
            ConnectionError: If encryption key is not found
            TimeoutError: If connection cannot be acquired within timeout
        """
        conn_wrapper = self._acquire()
        try:
            yield conn_wrapper.conn
        finally:
            self._return(conn_wrapper)

    def _acquire(self) -> _PooledConnection:
        """Acquire a connection from the pool or create a new one."""
        # Try to get from pool without blocking first
        try:
            conn_wrapper = self._pool.get_nowait()
            # Check if connection is too old
            if time.time() - conn_wrapper.created_at > self._max_lifetime:
                log.debug("Closing stale connection from pool")
                conn_wrapper.conn.close()
                # Create new connection
                return self._create_connection()
            return conn_wrapper
        except queue.Empty:
            # Pool is empty, try to create new connection
            pass

        # Create new connection under lock to prevent race condition
        with self._lock:
            if self._created_connections < self._pool_size:
                return self._create_connection()

        # Pool is full, wait with timeout for a connection to become available
        try:
            return self._pool.get(timeout=self._acquire_timeout)
        except queue.Empty:
            raise TimeoutError(
                f"Could not acquire database connection within {self._acquire_timeout} seconds"
            )

    def _return(self, conn_wrapper: _PooledConnection) -> None:
        """Return a connection to the pool."""
        try:
            self._pool.put_nowait(conn_wrapper)
        except queue.Full:
            # Pool is full, close the connection
            conn_wrapper.conn.close()
            with self._lock:
                self._created_connections -= 1

    def _create_connection(self) -> _PooledConnection:
        """Create a new encrypted database connection."""
        # Get encryption key from keyring
        encryption_key = self._crypto.get_key()
        if encryption_key is None:
            raise ConnectionError(
                "Database encryption key not found in keyring. "
                "This may indicate a corrupted installation or data migration issue."
            )

        # Connect with SQLCipher
        # check_same_thread=False allows connections to be safely reused across threads
        # by the connection pool, which is thread-safe via locks
        conn = sqlite3.connect(self._db_path, check_same_thread=False)

        # Set encryption key (must be done IMMEDIATELY after connection)
        conn.execute(f"PRAGMA key = \"x'{encryption_key.hex()}'\"")

        # Verify database is accessible (wrong key will cause error)
        try:
            conn.execute("SELECT count(*) FROM sqlite_master")
        except sqlite3.DatabaseError as e:
            conn.close()
            raise ConnectionError(
                f"Cannot decrypt database. Wrong encryption key or corrupted database. Error: {e}"
            )

        # Set encryption parameters
        conn.execute("PRAGMA cipher_memory_security = ON")
        conn.execute("PRAGMA cipher_page_size = 4096")
        conn.execute("PRAGMA cipher_kdf_iter = 256000")
        # Set busy timeout to handle concurrent access (30 seconds)
        conn.execute("PRAGMA busy_timeout = 30000")

        # Enable REGEXP function
        def regexp(expr, item):
            return re.search(expr, item) is not None if item else False

        conn.create_function("REGEXP", 2, regexp)

        with self._lock:
            self._created_connections += 1

        return _PooledConnection(conn, time.time())

    def close_all(self) -> None:
        """Close all connections in the pool."""
        while not self._pool.empty():
            try:
                conn_wrapper = self._pool.get_nowait()
                conn_wrapper.conn.close()
                with self._lock:
                    self._created_connections -= 1
            except queue.Empty:
                break
        log.debug("All pooled connections closed")


class SQLiteAdapter(DatabaseAdapter):
    """SQLite/SQLCipher database adapter implementation."""

    def __init__(self, db_path: Path, crypto):
        """Initialize SQLite adapter.

        Args:
            db_path: Path to SQLite database file
            crypto: CryptoManager instance for encryption key retrieval
        """
        self.db_path = db_path
        self.crypto = crypto
        self._connection_pool: ConnectionPool | None = None

        # Initialize cache for all-time statistics
        self._cache_all_time_typing_sec = 0
        self._cache_all_time_keystrokes = 0
        self._cache_all_time_bursts = 0

    def initialize(self) -> None:
        """Initialize database schema and perform migrations."""
        # Check if this is a fresh database
        is_fresh_install = not self.db_path.exists()

        # Initialize connection pool
        self._connection_pool = ConnectionPool(
            db_path=self.db_path,
            crypto=self.crypto,
            pool_size=10,
            max_lifetime_sec=300,
            acquire_timeout=30.0,
        )

        # For fresh install, generate encryption key first
        if is_fresh_install:
            try:
                self.crypto.initialize_database_key()
                log.info("Generated new encryption key for database")
            except RuntimeError as e:
                # If key already exists, that's fine - user is doing a reinstall
                if "already exists" not in str(e):
                    raise

        with self.get_connection() as conn:
            self._create_bursts_table(conn)
            self._create_statistics_table(conn)
            self._create_digraph_statistics_table(conn)
            self._create_high_scores_table(conn)
            self._create_daily_summaries_table(conn)
            self._create_word_statistics_table(conn)
            self._create_ignored_words_table(conn)
            self._migrate_high_scores_duration_ms(conn)
            self._add_word_statistics_columns()
            self._add_backspace_tracking_to_bursts(conn)
            self._migrate_bursts_unique_start_time(conn)
            self._migrate_high_scores_unique_timestamp(conn)
            conn.commit()

        # Initialize cache
        self._refresh_all_time_cache()

    @contextmanager
    def get_connection(self):
        """Get a database connection from the connection pool."""
        if self._connection_pool is None:
            raise AdapterError("Adapter not initialized. Call initialize() first.")
        with self._connection_pool.get_connection() as conn:
            yield conn

    def close(self) -> None:
        """Close all database connections and cleanup resources."""
        if self._connection_pool:
            self._connection_pool.close_all()

    # ========== Table Creation ==========

    def _create_bursts_table(self, conn: sqlite3.Connection) -> None:
        """Create bursts table."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bursts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_time INTEGER NOT NULL UNIQUE,
                end_time INTEGER NOT NULL,
                key_count INTEGER NOT NULL,
                duration_ms INTEGER NOT NULL,
                avg_wpm REAL,
                qualifies_for_high_score INTEGER DEFAULT 0
            )
        """)

    def _create_statistics_table(self, conn: sqlite3.Connection) -> None:
        """Create statistics table."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS statistics (
                keycode INTEGER NOT NULL,
                key_name TEXT NOT NULL,
                layout TEXT NOT NULL,
                avg_press_time REAL,
                total_presses INTEGER,
                slowest_ms REAL,
                fastest_ms REAL,
                last_updated INTEGER,
                PRIMARY KEY (keycode, layout)
            )
        """)

    def _create_digraph_statistics_table(self, conn: sqlite3.Connection) -> None:
        """Create digraph_statistics table."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS digraph_statistics (
                first_keycode INTEGER NOT NULL,
                second_keycode INTEGER NOT NULL,
                first_key TEXT NOT NULL,
                second_key TEXT NOT NULL,
                layout TEXT NOT NULL,
                avg_interval_ms REAL NOT NULL,
                total_sequences INTEGER NOT NULL DEFAULT 1,
                slowest_ms REAL,
                fastest_ms REAL,
                last_updated INTEGER,
                PRIMARY KEY (first_keycode, second_keycode, layout)
            )
        """)

    def _create_high_scores_table(self, conn: sqlite3.Connection) -> None:
        """Create high_scores table."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS high_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                fastest_burst_wpm REAL,
                burst_duration_sec REAL,
                burst_key_count INTEGER,
                timestamp INTEGER NOT NULL UNIQUE,
                burst_duration_ms INTEGER
            )
        """)

    def _create_daily_summaries_table(self, conn: sqlite3.Connection) -> None:
        """Create daily_summaries table."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_summaries (
                date TEXT PRIMARY KEY,
                total_keystrokes INTEGER,
                total_bursts INTEGER,
                avg_wpm REAL,
                slowest_keycode INTEGER,
                slowest_key_name TEXT,
                total_typing_sec INTEGER,
                summary_sent INTEGER DEFAULT 0
            )
        """)

    def _create_word_statistics_table(self, conn: sqlite3.Connection) -> None:
        """Create word_statistics table."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS word_statistics (
                word TEXT NOT NULL,
                layout TEXT NOT NULL,
                avg_speed_ms_per_letter REAL NOT NULL,
                total_letters INTEGER NOT NULL,
                total_duration_ms INTEGER NOT NULL,
                observation_count INTEGER NOT NULL,
                last_seen INTEGER NOT NULL,
                backspace_count INTEGER DEFAULT 0,
                editing_time_ms INTEGER DEFAULT 0,
                PRIMARY KEY (word, layout)
            )
        """)

    def _create_ignored_words_table(self, conn: sqlite3.Connection) -> None:
        """Create ignored_words table for hash-based word filtering."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ignored_words (
                word_hash TEXT PRIMARY KEY,
                added_at INTEGER NOT NULL
            )
        """)

    def _add_word_statistics_columns(self) -> None:
        """Add new columns to word_statistics table if they don't exist."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            try:
                cursor.execute("""
                    ALTER TABLE word_statistics ADD COLUMN backspace_count INTEGER DEFAULT 0
                """)
                log.info("Added backspace_count column to word_statistics")
            except sqlite3.OperationalError as e:
                if "duplicate column" in str(e):
                    pass
                else:
                    log.error(f"Error adding backspace_count column: {e}")

            try:
                cursor.execute("""
                    ALTER TABLE word_statistics ADD COLUMN editing_time_ms INTEGER DEFAULT 0
                """)
                log.info("Added editing_time_ms column to word_statistics")
            except sqlite3.OperationalError as e:
                if "duplicate column" in str(e):
                    pass
                else:
                    log.error(f"Error adding editing_time_ms column: {e}")

            conn.commit()

    def _add_backspace_tracking_to_bursts(self, conn: sqlite3.Connection) -> None:
        """Add backspace_count and net_key_count columns to bursts table."""
        cursor = conn.cursor()

        try:
            cursor.execute("""
                ALTER TABLE bursts ADD COLUMN backspace_count INTEGER DEFAULT 0
            """)
            log.info("Added backspace_count column to bursts table")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e):
                pass
            else:
                log.error(f"Error adding backspace_count to bursts: {e}")

        try:
            cursor.execute("""
                ALTER TABLE bursts ADD COLUMN net_key_count INTEGER DEFAULT 0
            """)
            log.info("Added net_key_count column to bursts table")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e):
                pass
            else:
                log.error(f"Error adding net_key_count to bursts: {e}")

        conn.commit()

    def _migrate_high_scores_duration_ms(self, conn: sqlite3.Connection) -> None:
        """Migrate high_scores table to use duration_ms instead of duration_sec."""
        cursor = conn.cursor()

        # Check if burst_duration_ms column exists
        cursor.execute("""
            SELECT COUNT(*) FROM pragma_table_info('high_scores')
            WHERE name='burst_duration_ms'
        """)
        has_column = cursor.fetchone()[0] > 0

        if not has_column:
            # Add new column
            cursor.execute("""
                ALTER TABLE high_scores ADD COLUMN burst_duration_ms INTEGER
            """)
            log.info("Added burst_duration_ms column to high_scores table")

            # Migrate existing data
            cursor.execute("""
                UPDATE high_scores
                SET burst_duration_ms = CAST(burst_duration_sec * 1000 AS INTEGER)
                WHERE burst_duration_ms IS NULL
            """)
            log.info("Migrated high_scores data from duration_sec to duration_ms")

    def _migrate_bursts_unique_start_time(self, conn: sqlite3.Connection) -> None:
        """Migrate bursts table to add UNIQUE constraint on start_time.

        Since SQLite doesn't support adding UNIQUE constraints directly,
        we need to recreate the table and copy data.
        """
        cursor = conn.cursor()

        # Check if UNIQUE constraint already exists by checking the table schema
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='bursts'")
        schema = cursor.fetchone()

        if schema and "UNIQUE" in schema[0]:
            # Already has UNIQUE constraint
            return

        # Check if there are duplicate start_time values
        cursor.execute(
            "SELECT start_time, COUNT(*) FROM bursts GROUP BY start_time HAVING COUNT(*) > 1"
        )
        duplicates = cursor.fetchall()

        if duplicates:
            log.warning(
                f"Found {len(duplicates)} duplicate start_time values in bursts table. Removing oldest duplicates."
            )
            # For each duplicate, keep the one with the highest ID (most recent)
            for start_time, count in duplicates:
                cursor.execute(
                    """
                    DELETE FROM bursts
                    WHERE start_time = ? AND id NOT IN (
                        SELECT id FROM bursts WHERE start_time = ? ORDER BY id DESC LIMIT 1
                    )
                """,
                    (start_time, start_time),
                )

        # Recreate the table with UNIQUE constraint
        cursor.execute("""
            CREATE TABLE bursts_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_time INTEGER NOT NULL UNIQUE,
                end_time INTEGER NOT NULL,
                key_count INTEGER NOT NULL,
                duration_ms INTEGER NOT NULL,
                avg_wpm REAL,
                qualifies_for_high_score INTEGER DEFAULT 0,
                backspace_count INTEGER DEFAULT 0,
                net_key_count INTEGER DEFAULT 0
            )
        """)

        # Copy data from old table to new table
        cursor.execute("""
            INSERT INTO bursts_new
            (id, start_time, end_time, key_count, duration_ms, avg_wpm, qualifies_for_high_score, backspace_count, net_key_count)
            SELECT id, start_time, end_time, key_count, duration_ms, avg_wpm, qualifies_for_high_score,
                   COALESCE(backspace_count, 0), COALESCE(net_key_count, 0)
            FROM bursts
        """)

        # Drop old table and rename new table
        cursor.execute("DROP TABLE bursts")
        cursor.execute("ALTER TABLE bursts_new RENAME TO bursts")

        log.info("Added UNIQUE constraint on bursts.start_time")

    def _migrate_high_scores_unique_timestamp(self, conn: sqlite3.Connection) -> None:
        """Migrate high_scores table to add UNIQUE constraint on timestamp.

        Since SQLite doesn't support adding UNIQUE constraints directly,
        we need to recreate the table and copy data.
        """
        cursor = conn.cursor()

        # Check if UNIQUE constraint already exists by checking the table schema
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='high_scores'")
        schema = cursor.fetchone()

        if schema and "UNIQUE" in schema[0]:
            # Already has UNIQUE constraint
            return

        # Check if there are duplicate timestamp values
        cursor.execute(
            "SELECT timestamp, COUNT(*) FROM high_scores GROUP BY timestamp HAVING COUNT(*) > 1"
        )
        duplicates = cursor.fetchall()

        if duplicates:
            log.warning(
                f"Found {len(duplicates)} duplicate timestamp values in high_scores table. Removing oldest duplicates."
            )
            # For each duplicate, keep the one with the highest ID (most recent)
            for timestamp, count in duplicates:
                cursor.execute(
                    """
                    DELETE FROM high_scores
                    WHERE timestamp = ? AND id NOT IN (
                        SELECT id FROM high_scores WHERE timestamp = ? ORDER BY id DESC LIMIT 1
                    )
                """,
                    (timestamp, timestamp),
                )

        # Recreate the table with UNIQUE constraint
        cursor.execute("""
            CREATE TABLE high_scores_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                fastest_burst_wpm REAL,
                burst_duration_sec REAL,
                burst_key_count INTEGER,
                timestamp INTEGER NOT NULL UNIQUE,
                burst_duration_ms INTEGER
            )
        """)

        # Copy data from old table to new table
        cursor.execute("""
            INSERT INTO high_scores_new
            (id, date, fastest_burst_wpm, burst_duration_sec, burst_key_count, timestamp, burst_duration_ms)
            SELECT id, date, fastest_burst_wpm, burst_duration_sec, burst_key_count, timestamp, burst_duration_ms
            FROM high_scores
        """)

        # Drop old table and rename new table
        cursor.execute("DROP TABLE high_scores")
        cursor.execute("ALTER TABLE high_scores_new RENAME TO high_scores")

        log.info("Added UNIQUE constraint on high_scores.timestamp")

    def _refresh_all_time_cache(self) -> None:
        """Refresh all-time statistics cache from database."""
        import time

        start = time.time()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COALESCE(SUM(duration_ms), 0) FROM bursts")
            total_ms = cursor.fetchone()[0]
            self._cache_all_time_typing_sec = int(total_ms / 1000)

            cursor.execute("SELECT COALESCE(SUM(net_key_count), 0) FROM bursts")
            self._cache_all_time_keystrokes = int(cursor.fetchone()[0])

            cursor.execute("SELECT COUNT(*) FROM bursts")
            self._cache_all_time_bursts = int(cursor.fetchone()[0])

        elapsed = (time.time() - start) * 1000
        if elapsed > 10:  # Log if takes more than 10ms
            log.warning(
                f"_refresh_all_time_cache took {elapsed:.1f}ms (bursts: {self._cache_all_time_bursts})"
            )

    # ========== Burst Operations ==========

    def store_burst(
        self,
        start_time: int,
        end_time: int,
        key_count: int,
        backspace_count: int,
        net_key_count: int,
        duration_ms: int,
        avg_wpm: float,
        qualifies_for_high_score: bool,
    ) -> None:
        """Store a burst record."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO bursts
                (start_time, end_time, key_count, backspace_count, net_key_count, duration_ms, avg_wpm, qualifies_for_high_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    start_time,
                    end_time,
                    key_count,
                    backspace_count,
                    net_key_count,
                    duration_ms,
                    avg_wpm,
                    int(qualifies_for_high_score),
                ),
            )
            conn.commit()

            # Only update cache if the burst was actually inserted (not a duplicate)
            if cursor.rowcount > 0:
                self._cache_all_time_typing_sec += duration_ms // 1000
                self._cache_all_time_keystrokes += net_key_count
                self._cache_all_time_bursts += 1

    def batch_insert_bursts(self, bursts: list[dict]) -> int:
        """Batch insert burst records.

        Args:
            bursts: List of burst dictionaries

        Returns:
            Number of records actually inserted (excluding duplicates)
        """
        if not bursts:
            return 0

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Prepare data tuples
            data_tuples = []

            for b in bursts:
                data_tuples.append(
                    (
                        b.get("start_time", 0),
                        b.get("end_time", 0),
                        b.get("key_count", 0),
                        b.get("backspace_count", 0),
                        b.get("net_key_count", 0),
                        b.get("duration_ms", 0),
                        b.get("avg_wpm", 0.0),
                        1 if b.get("qualifies_for_high_score") else 0,
                    )
                )

            # Use INSERT OR IGNORE to skip duplicates
            # With UNIQUE constraint on start_time, duplicates will be ignored
            cursor.executemany(
                """
                INSERT OR IGNORE INTO bursts
                (start_time, end_time, key_count, backspace_count, net_key_count,
                 duration_ms, avg_wpm, qualifies_for_high_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                data_tuples,
            )

            conn.commit()

            # rowcount gives the actual number of inserted rows
            inserted_count = cursor.rowcount

            # Recalculate cache for accuracy
            if inserted_count > 0:
                self._refresh_all_time_cache()

            return inserted_count

    def get_bursts_for_timeseries(self, start_ms: int, end_ms: int) -> list[BurstTimeSeries]:
        """Get burst data for time-series graph."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT start_time, avg_wpm
                FROM bursts
                WHERE start_time >= ? AND start_time < ?
                ORDER BY start_time
            """,
                (start_ms, end_ms),
            )
            rows = cursor.fetchall()
            return [BurstTimeSeries(timestamp_ms=r[0], avg_wpm=r[1]) for r in rows]

    def get_burst_wpm_histogram(self, bin_count: int = 50) -> list[tuple[float, int]]:
        """Get burst WPM distribution as histogram data."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Get all WPM values
            cursor.execute("SELECT avg_wpm FROM bursts WHERE avg_wpm IS NOT NULL ORDER BY avg_wpm")
            wpm_values = [row[0] for row in cursor.fetchall()]

            if not wpm_values:
                return []

            # Calculate range
            min_wpm = wpm_values[0]
            max_wpm = wpm_values[-1]

            if min_wpm == max_wpm:
                return [(min_wpm, len(wpm_values))]

            # Calculate bin width
            bin_width = (max_wpm - min_wpm) / bin_count

            # Initialize bins
            bins = [0] * bin_count

            # Assign values to bins
            for wpm in wpm_values:
                bin_index = min(int((wpm - min_wpm) / bin_width), bin_count - 1)
                bins[bin_index] += 1

            # Calculate bin centers
            bin_centers = [min_wpm + (i + 0.5) * bin_width for i in range(bin_count)]

            # Filter empty bins
            return [
                (center, count)
                for center, count in zip(bin_centers, bins, strict=False)
                if count > 0
            ]

    def get_recent_bursts(self, limit: int = 3) -> list[tuple[int, float, int, int, int, int, str]]:
        """Get the most recent bursts."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT
                    id,
                    avg_wpm,
                    net_key_count,
                    duration_ms,
                    COALESCE(backspace_count, 0) as backspace_count,
                    start_time
                FROM bursts
                ORDER BY start_time DESC
                LIMIT ?
            """,
                (limit,),
            )

            bursts = []
            for row in cursor.fetchall():
                (
                    burst_id,
                    wpm,
                    net_chars,
                    duration_ms,
                    backspaces,
                    start_time_ms,
                ) = row

                # Format time as readable string
                try:
                    dt = datetime.fromtimestamp(start_time_ms / 1000)
                    time_str = dt.strftime("%H:%M:%S")
                except (ValueError, OSError):
                    time_str = "??"

                bursts.append(
                    (
                        burst_id,
                        wpm,
                        net_chars,
                        duration_ms,
                        backspaces,
                        start_time_ms,
                        time_str,
                    )
                )

            return bursts

    def get_burst_duration_stats_ms(self) -> tuple[int, int, int, int]:
        """Get burst duration statistics across all bursts.

        Returns:
            Tuple of (avg_ms, min_ms, max_ms, percentile_95_ms)
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COALESCE(AVG(duration_ms), 0),
                       COALESCE(MIN(duration_ms), 0),
                       COALESCE(MAX(duration_ms), 0)
                FROM bursts
            """
            )
            result = cursor.fetchone()
            if result and result[0]:
                avg_ms = int(result[0])
                min_ms = int(result[1])
                max_ms = int(result[2])

                # Calculate 95th percentile using OFFSET
                cursor.execute(
                    """
                    SELECT duration_ms FROM bursts
                    ORDER BY duration_ms
                    LIMIT 1 OFFSET (SELECT CAST(COUNT(*) * 95 / 100.0 AS INT) FROM bursts) - 1
                """
                )
                percentile_result = cursor.fetchone()
                percentile_95_ms = int(percentile_result[0]) if percentile_result else 0

                return (avg_ms, min_ms, max_ms, percentile_95_ms)
            return (0, 0, 0, 0)

    def get_burst_stats_for_date_range(self, start_ms: int, end_ms: int) -> tuple[int, int]:
        """Get burst statistics for a date range."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Calculate keystrokes from bursts (sum of net_key_count)
            cursor.execute(
                """
                SELECT COALESCE(SUM(net_key_count), 0) FROM bursts
                WHERE start_time >= ? AND start_time < ?
            """,
                (start_ms, end_ms),
            )
            total_keystrokes = cursor.fetchone()[0]

            # Count bursts
            cursor.execute(
                """
                SELECT COUNT(*) FROM bursts
                WHERE start_time >= ? AND start_time < ?
            """,
                (start_ms, end_ms),
            )
            total_bursts = cursor.fetchone()[0]

            return (total_keystrokes, total_bursts)

    def get_burst_wpms_for_threshold(self, start_ms: int, min_duration_ms: int) -> list[float]:
        """Get burst WPMS for threshold calculation."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT avg_wpm FROM bursts
                WHERE start_time >= ? AND duration_ms >= ?
                ORDER BY avg_wpm ASC
            """,
                (start_ms, min_duration_ms),
            )
            return [row[0] for row in cursor.fetchall()]

    def get_total_burst_duration(self, start_ms: int, end_ms: int) -> int:
        """Get total burst duration for a date range."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COALESCE(SUM(duration_ms), 0) FROM bursts
                WHERE start_time >= ? AND start_time < ?
            """,
                (start_ms, end_ms),
            )
            return cursor.fetchone()[0]

    def get_typing_time_by_granularity(
        self,
        granularity: str,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 90,
    ) -> list[TypingTimeDataPoint]:
        """Get typing time aggregated by time granularity."""
        # Calculate date range
        if end_date:
            end_ms = int(
                (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)).timestamp() * 1000
            )
        else:
            end_ms = int(time.time() * 1000)

        if start_date:
            start_ms = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
        else:
            # Default to showing limit periods
            if granularity == "day":
                start_ms = end_ms - (limit * 86400000)
            elif granularity == "week":
                start_ms = end_ms - (limit * 7 * 86400000)
            elif granularity == "month":
                start_ms = end_ms - (limit * 30 * 86400000)
            elif granularity == "quarter":
                start_ms = end_ms - (limit * 90 * 86400000)
            else:
                start_ms = end_ms - (limit * 86400000)

        # Build query based on granularity
        if granularity == "day":
            group_by = "strftime('%Y-%m-%d', (start_time / 1000), 'unixepoch')"
        elif granularity == "week":
            group_by = "strftime('%Y-%W', (start_time / 1000), 'unixepoch')"
        elif granularity == "month":
            group_by = "strftime('%Y-%m', (start_time / 1000), 'unixepoch')"
        elif granularity == "quarter":
            group_by = "strftime('%Y-', (start_time / 1000), 'unixepoch') || ((CAST(strftime('%m', (start_time / 1000), 'unixepoch') AS INTEGER) - 1) / 3 + 1)"
        else:
            log.warning(f"Unknown granularity: {granularity}, defaulting to day")
            group_by = "strftime('%Y-%m-%d', (start_time / 1000), 'unixepoch')"

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT
                    {group_by} AS period_key,
                    MIN(start_time) AS period_start_ms,
                    SUM(duration_ms) AS total_typing_ms,
                    COUNT(*) AS total_bursts,
                    AVG(avg_wpm) AS avg_wpm
                FROM bursts
                WHERE start_time >= ? AND start_time < ?
                GROUP BY period_key
                ORDER BY period_start_ms
                LIMIT ?
            """,
                (start_ms, end_ms, limit),
            )
            rows = cursor.fetchall()

            results = []
            for r in rows:
                period_key = r[0]
                period_start_ms = int(r[1])
                total_typing_ms = int(r[2])
                total_bursts = int(r[3])
                avg_wpm = float(r[4]) if r[4] else 0.0

                # Calculate period end based on granularity
                period_end_ms = self._calculate_period_end(period_start_ms, granularity)

                # Format period label from period_key
                if granularity == "day":
                    period_label = period_key
                elif granularity == "week":
                    year, week = period_key.split("-")
                    period_label = f"{year}-W{week}"
                elif granularity == "month":
                    period_label = period_key
                elif granularity == "quarter":
                    year, quarter = period_key.split("-")
                    period_label = f"{year}-Q{quarter}"
                else:
                    period_label = period_key

                results.append(
                    TypingTimeDataPoint(
                        period_start=period_start_ms,
                        period_end=period_end_ms,
                        period_label=period_label,
                        total_typing_ms=total_typing_ms,
                        total_bursts=total_bursts,
                        avg_wpm=avg_wpm,
                    )
                )

            return results

    def _calculate_period_end(self, period_start_ms: int, granularity: str) -> int:
        """Calculate the end timestamp for a period."""
        start_dt = datetime.fromtimestamp(period_start_ms / 1000)

        if granularity == "day":
            end_dt = start_dt + timedelta(days=1)
        elif granularity == "week":
            end_dt = start_dt + timedelta(weeks=1)
        elif granularity == "month":
            if start_dt.month == 12:
                end_dt = start_dt.replace(year=start_dt.year + 1, month=1)
            else:
                end_dt = start_dt.replace(month=start_dt.month + 1)
        elif granularity == "quarter":
            month = start_dt.month
            year = start_dt.year
            if month <= 9:
                new_month = month + 3
                new_year = year
            else:
                new_month = month - 9
                new_year = year + 1
            end_dt = start_dt.replace(year=new_year, month=new_month)
        else:
            end_dt = start_dt + timedelta(days=1)

        return int(end_dt.timestamp() * 1000)

    # ========== Key Statistics Operations ==========

    def update_key_statistics(
        self, keycode: int, key_name: str, layout: str, press_time_ms: float
    ) -> None:
        """Update statistics for a key."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT avg_press_time, total_presses, slowest_ms, fastest_ms
                FROM statistics WHERE keycode = ? AND layout = ?
            """,
                (keycode, layout),
            )

            result = cursor.fetchone()
            now_ms = int(time.time() * 1000)

            if result:
                avg_press, total_presses, slowest_ms, fastest_ms = result
                new_total = total_presses + 1

                new_avg = (avg_press * total_presses + press_time_ms) / new_total
                new_slowest = min(slowest_ms, press_time_ms)
                new_fastest = max(fastest_ms, press_time_ms)

                cursor.execute(
                    """
                    UPDATE statistics SET
                        avg_press_time = ?, total_presses = ?, slowest_ms = ?,
                        fastest_ms = ?, last_updated = ?
                    WHERE keycode = ? AND layout = ?
                """,
                    (
                        new_avg,
                        new_total,
                        new_slowest,
                        new_fastest,
                        now_ms,
                        keycode,
                        layout,
                    ),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO statistics
                    (keycode, key_name, layout, avg_press_time, total_presses,
                     slowest_ms, fastest_ms, last_updated)
                    VALUES (?, ?, ?, ?, 1, ?, ?, ?)
                """,
                    (
                        keycode,
                        key_name,
                        layout,
                        press_time_ms,
                        press_time_ms,
                        press_time_ms,
                        now_ms,
                    ),
                )

            conn.commit()

    def batch_insert_statistics(self, records: list[dict]) -> int:
        """Batch insert statistics records.

        Args:
            records: List of statistics dictionaries

        Returns:
            Number of records actually inserted (excluding duplicates)
        """
        if not records:
            return 0

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Get count before insert
            cursor.execute("SELECT COUNT(*) FROM statistics")
            before_count = cursor.fetchone()[0]

            # Prepare data tuples
            data_tuples = []
            for r in records:
                data_tuples.append(
                    (
                        r.get("keycode"),
                        r.get("key_name"),
                        r.get("layout"),
                        r.get("avg_press_time"),
                        r.get("total_presses"),
                        r.get("slowest_ms"),
                        r.get("fastest_ms"),
                        r.get("last_updated"),
                    )
                )

            # Use executemany for efficient bulk insert
            cursor.executemany(
                """
                INSERT OR IGNORE INTO statistics
                (keycode, key_name, layout, avg_press_time, total_presses,
                 slowest_ms, fastest_ms, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                data_tuples,
            )

            conn.commit()

            # Get count after insert to determine actual inserted count
            cursor.execute("SELECT COUNT(*) FROM statistics")
            after_count = cursor.fetchone()[0]

            return after_count - before_count

    def get_slowest_keys(self, limit: int = 10, layout: str | None = None) -> list[KeyPerformance]:
        """Get slowest keys (highest average press time)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if layout:
                cursor.execute(
                    """
                    SELECT s.keycode, s.key_name, s.avg_press_time, freq_rank.rank
                    FROM statistics s
                    INNER JOIN (
                        SELECT key_name, ROW_NUMBER() OVER (ORDER BY total_presses DESC) as rank
                        FROM statistics
                        WHERE layout = ? AND (key_name REGEXP '^[a-z]$' OR key_name IN ('ä', 'ö', 'ü', 'ß'))
                    ) freq_rank ON s.key_name = freq_rank.key_name
                    WHERE s.layout = ? AND s.total_presses >= 2
                        AND (s.key_name REGEXP '^[a-z]$' OR s.key_name IN ('ä', 'ö', 'ü', 'ß'))
                    ORDER BY s.avg_press_time DESC
                    LIMIT ?
                """,
                    (layout, layout, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT s.keycode, s.key_name, s.avg_press_time, freq_rank.rank
                    FROM statistics s
                    INNER JOIN (
                        SELECT key_name, ROW_NUMBER() OVER (ORDER BY total_presses DESC) as rank
                        FROM statistics
                        WHERE (key_name REGEXP '^[a-z]$' OR key_name IN ('ä', 'ö', 'ü', 'ß'))
                    ) freq_rank ON s.key_name = freq_rank.key_name
                    WHERE s.total_presses >= 2
                        AND (s.key_name REGEXP '^[a-z]$' OR s.key_name IN ('ä', 'ö', 'ü', 'ß'))
                    ORDER BY s.avg_press_time DESC
                    LIMIT ?
                """,
                    (limit,),
                )
            rows = cursor.fetchall()
            return [
                KeyPerformance(keycode=r[0], key_name=r[1], avg_press_time=r[2], rank=r[3])
                for r in rows
            ]

    def get_fastest_keys(self, limit: int = 10, layout: str | None = None) -> list[KeyPerformance]:
        """Get fastest keys (lowest average press time)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if layout:
                cursor.execute(
                    """
                    SELECT s.keycode, s.key_name, s.avg_press_time, freq_rank.rank
                    FROM statistics s
                    INNER JOIN (
                        SELECT key_name, ROW_NUMBER() OVER (ORDER BY total_presses DESC) as rank
                        FROM statistics
                        WHERE layout = ? AND (key_name REGEXP '^[a-z]$' OR key_name IN ('ä', 'ö', 'ü', 'ß'))
                    ) freq_rank ON s.key_name = freq_rank.key_name
                    WHERE s.layout = ? AND s.total_presses >= 2
                        AND (s.key_name REGEXP '^[a-z]$' OR s.key_name IN ('ä', 'ö', 'ü', 'ß'))
                    ORDER BY s.avg_press_time ASC
                    LIMIT ?
                """,
                    (layout, layout, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT s.keycode, s.key_name, s.avg_press_time, freq_rank.rank
                    FROM statistics s
                    INNER JOIN (
                        SELECT key_name, ROW_NUMBER() OVER (ORDER BY total_presses DESC) as rank
                        FROM statistics
                        WHERE (key_name REGEXP '^[a-z]$' OR key_name IN ('ä', 'ö', 'ü', 'ß'))
                    ) freq_rank ON s.key_name = freq_rank.key_name
                    WHERE s.total_presses >= 2
                        AND (s.key_name REGEXP '^[a-z]$' OR s.key_name IN ('ä', 'ö', 'ü', 'ß'))
                    ORDER BY s.avg_press_time ASC
                    LIMIT ?
                """,
                    (limit,),
                )
            rows = cursor.fetchall()
            return [
                KeyPerformance(keycode=r[0], key_name=r[1], avg_press_time=r[2], rank=r[3])
                for r in rows
            ]

    # ========== Digraph Statistics Operations ==========

    def update_digraph_statistics(
        self,
        first_keycode: int,
        second_keycode: int,
        first_key: str,
        second_key: str,
        layout: str,
        interval_ms: float,
    ) -> None:
        """Update statistics for a digraph."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT avg_interval_ms, total_sequences, slowest_ms, fastest_ms
                FROM digraph_statistics
                WHERE first_keycode = ? AND second_keycode = ? AND layout = ?
            """,
                (first_keycode, second_keycode, layout),
            )

            result = cursor.fetchone()
            now_ms = int(time.time() * 1000)

            if result:
                avg_interval, total_sequences, slowest_ms, fastest_ms = result
                new_total = total_sequences + 1

                # Calculate running average
                new_avg = (avg_interval * total_sequences + interval_ms) / new_total
                new_slowest = max(slowest_ms, interval_ms)
                new_fastest = min(fastest_ms, interval_ms)

                cursor.execute(
                    """
                    UPDATE digraph_statistics SET
                        avg_interval_ms = ?, total_sequences = ?, slowest_ms = ?,
                        fastest_ms = ?, last_updated = ?
                    WHERE first_keycode = ? AND second_keycode = ? AND layout = ?
                """,
                    (
                        new_avg,
                        new_total,
                        new_slowest,
                        new_fastest,
                        now_ms,
                        first_keycode,
                        second_keycode,
                        layout,
                    ),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO digraph_statistics
                    (first_keycode, second_keycode, first_key, second_key, layout,
                     avg_interval_ms, total_sequences, slowest_ms, fastest_ms, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
                """,
                    (
                        first_keycode,
                        second_keycode,
                        first_key,
                        second_key,
                        layout,
                        interval_ms,
                        interval_ms,
                        interval_ms,
                        now_ms,
                    ),
                )

            conn.commit()

    def get_slowest_digraphs(
        self, limit: int = 10, layout: str | None = None
    ) -> list[DigraphPerformance]:
        """Get slowest digraphs (highest average interval)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if layout:
                cursor.execute(
                    """
                    SELECT ds.first_key, ds.second_key, ds.avg_interval_ms, freq_rank.rank
                    FROM digraph_statistics ds
                    INNER JOIN (
                        SELECT first_key || second_key as digraph,
                               ROW_NUMBER() OVER (ORDER BY total_sequences DESC) as rank
                        FROM digraph_statistics
                        WHERE layout = ?
                    ) freq_rank ON ds.first_key || ds.second_key = freq_rank.digraph
                    WHERE ds.layout = ? AND ds.total_sequences >= 2
                    ORDER BY ds.avg_interval_ms DESC
                    LIMIT ?
                """,
                    (layout, layout, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT ds.first_key, ds.second_key, ds.avg_interval_ms, freq_rank.rank
                    FROM digraph_statistics ds
                    INNER JOIN (
                        SELECT first_key || second_key as digraph,
                               ROW_NUMBER() OVER (ORDER BY total_sequences DESC) as rank
                        FROM digraph_statistics
                    ) freq_rank ON ds.first_key || ds.second_key = freq_rank.digraph
                    WHERE ds.total_sequences >= 2
                    ORDER BY ds.avg_interval_ms DESC
                    LIMIT ?
                """,
                    (limit,),
                )
            rows = cursor.fetchall()
            return [
                DigraphPerformance(
                    first_key=r[0],
                    second_key=r[1],
                    avg_interval_ms=r[2],
                    wpm=60000 / (r[2] * 5) if r[2] > 0 else 0,
                    rank=r[3],
                )
                for r in rows
            ]

    def get_fastest_digraphs(
        self, limit: int = 10, layout: str | None = None
    ) -> list[DigraphPerformance]:
        """Get fastest digraphs (lowest average interval)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if layout:
                cursor.execute(
                    """
                    SELECT ds.first_key, ds.second_key, ds.avg_interval_ms, freq_rank.rank
                    FROM digraph_statistics ds
                    INNER JOIN (
                        SELECT first_key || second_key as digraph,
                               ROW_NUMBER() OVER (ORDER BY total_sequences DESC) as rank
                        FROM digraph_statistics
                        WHERE layout = ?
                    ) freq_rank ON ds.first_key || ds.second_key = freq_rank.digraph
                    WHERE ds.layout = ? AND ds.total_sequences >= 2
                    ORDER BY ds.avg_interval_ms ASC
                    LIMIT ?
                """,
                    (layout, layout, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT ds.first_key, ds.second_key, ds.avg_interval_ms, freq_rank.rank
                    FROM digraph_statistics ds
                    INNER JOIN (
                        SELECT first_key || second_key as digraph,
                               ROW_NUMBER() OVER (ORDER BY total_sequences DESC) as rank
                        FROM digraph_statistics
                    ) freq_rank ON ds.first_key || ds.second_key = freq_rank.digraph
                    WHERE ds.total_sequences >= 2
                    ORDER BY ds.avg_interval_ms ASC
                    LIMIT ?
                """,
                    (limit,),
                )
            rows = cursor.fetchall()
            return [
                DigraphPerformance(
                    first_key=r[0],
                    second_key=r[1],
                    avg_interval_ms=r[2],
                    wpm=60000 / (r[2] * 5) if r[2] > 0 else 0,
                    rank=r[3],
                )
                for r in rows
            ]

    # ========== Word Statistics Operations ==========

    def update_word_statistics(
        self,
        word: str,
        layout: str,
        duration_ms: int,
        num_letters: int,
        backspace_count: int = 0,
        editing_time_ms: int = 0,
    ) -> None:
        """Update statistics for a word."""
        speed_per_letter = duration_ms / num_letters
        now_ms = int(time.time() * 1000)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT avg_speed_ms_per_letter, total_letters,
                       total_duration_ms, observation_count,
                       backspace_count, editing_time_ms
                FROM word_statistics
                WHERE word = ? AND layout = ?
            """,
                (word, layout),
            )

            result = cursor.fetchone()

            if result:
                (
                    avg_speed,
                    total_letters,
                    total_duration,
                    count,
                    existing_backspace,
                    existing_editing_time,
                ) = result
                new_count = count + 1
                new_avg_speed = (avg_speed * count + speed_per_letter) / new_count
                new_total_letters = total_letters + num_letters
                new_total_duration = total_duration + duration_ms
                new_backspace = existing_backspace + backspace_count
                new_editing_time = existing_editing_time + editing_time_ms

                cursor.execute(
                    """
                    UPDATE word_statistics SET
                        avg_speed_ms_per_letter = ?,
                        total_letters = ?,
                        total_duration_ms = ?,
                        observation_count = ?,
                        last_seen = ?,
                        backspace_count = ?,
                        editing_time_ms = ?
                    WHERE word = ? AND layout = ?
                """,
                    (
                        new_avg_speed,
                        new_total_letters,
                        new_total_duration,
                        new_count,
                        now_ms,
                        new_backspace,
                        new_editing_time,
                        word,
                        layout,
                    ),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO word_statistics
                    (word, layout, avg_speed_ms_per_letter, total_letters,
                     total_duration_ms, observation_count, last_seen,
                     backspace_count, editing_time_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        word,
                        layout,
                        speed_per_letter,
                        num_letters,
                        duration_ms,
                        1,
                        now_ms,
                        backspace_count,
                        editing_time_ms,
                    ),
                )

            conn.commit()

    def batch_insert_word_statistics(self, records: list[dict]) -> int:
        """Batch insert word statistics records.

        Args:
            records: List of word statistics dictionaries

        Returns:
            Number of records actually inserted (excluding duplicates)
        """
        if not records:
            return 0

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Get count before insert
            cursor.execute("SELECT COUNT(*) FROM word_statistics")
            before_count = cursor.fetchone()[0]

            # Prepare data tuples
            data_tuples = []
            for r in records:
                data_tuples.append(
                    (
                        r.get("word"),
                        r.get("layout"),
                        r.get("avg_speed_ms_per_letter"),
                        r.get("total_letters"),
                        r.get("total_duration_ms"),
                        r.get("observation_count"),
                        r.get("last_seen"),
                        r.get("backspace_count", 0),
                        r.get("editing_time_ms", 0),
                    )
                )

            # Use executemany for efficient bulk insert
            cursor.executemany(
                """
                INSERT OR IGNORE INTO word_statistics
                (word, layout, avg_speed_ms_per_letter, total_letters,
                 total_duration_ms, observation_count, last_seen,
                 backspace_count, editing_time_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                data_tuples,
            )

            conn.commit()

            # Get count after insert to determine actual inserted count
            cursor.execute("SELECT COUNT(*) FROM word_statistics")
            after_count = cursor.fetchone()[0]

            return after_count - before_count

    def get_slowest_words(
        self, limit: int = 10, layout: str | None = None
    ) -> list[WordStatisticsLite]:
        """Get slowest words (highest average time per letter)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if layout:
                cursor.execute(
                    """
                    SELECT ws.word, ws.avg_speed_ms_per_letter,
                           ws.total_duration_ms, ws.total_letters,
                           freq_rank.rank
                    FROM word_statistics ws
                    INNER JOIN (
                        SELECT word, ROW_NUMBER() OVER (ORDER BY observation_count DESC) as rank
                        FROM word_statistics
                        WHERE layout = ?
                    ) freq_rank ON ws.word = freq_rank.word
                    WHERE ws.layout = ? AND ws.observation_count >= 2
                    ORDER BY ws.avg_speed_ms_per_letter DESC
                    LIMIT ?
                """,
                    (layout, layout, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT ws.word, ws.avg_speed_ms_per_letter,
                           ws.total_duration_ms, ws.total_letters,
                           freq_rank.rank
                    FROM word_statistics ws
                    INNER JOIN (
                        SELECT word, ROW_NUMBER() OVER (ORDER BY observation_count DESC) as rank
                        FROM word_statistics
                    ) freq_rank ON ws.word = freq_rank.word
                    WHERE ws.observation_count >= 2
                    ORDER BY ws.avg_speed_ms_per_letter DESC
                    LIMIT ?
                """,
                    (limit,),
                )
            rows = cursor.fetchall()
            return [
                WordStatisticsLite(
                    word=r[0],
                    avg_speed_ms_per_letter=r[1],
                    total_duration_ms=r[2],
                    total_letters=r[3],
                    rank=r[4],
                )
                for r in rows
            ]

    def get_fastest_words(
        self, limit: int = 10, layout: str | None = None
    ) -> list[WordStatisticsLite]:
        """Get fastest words (lowest average time per letter)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if layout:
                cursor.execute(
                    """
                    SELECT ws.word, ws.avg_speed_ms_per_letter,
                           ws.total_duration_ms, ws.total_letters,
                           freq_rank.rank
                    FROM word_statistics ws
                    INNER JOIN (
                        SELECT word, ROW_NUMBER() OVER (ORDER BY observation_count DESC) as rank
                        FROM word_statistics
                        WHERE layout = ?
                    ) freq_rank ON ws.word = freq_rank.word
                    WHERE ws.layout = ? AND ws.observation_count >= 2
                    ORDER BY ws.avg_speed_ms_per_letter ASC
                    LIMIT ?
                """,
                    (layout, layout, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT ws.word, ws.avg_speed_ms_per_letter,
                           ws.total_duration_ms, ws.total_letters,
                           freq_rank.rank
                    FROM word_statistics ws
                    INNER JOIN (
                        SELECT word, ROW_NUMBER() OVER (ORDER BY observation_count DESC) as rank
                        FROM word_statistics
                    ) freq_rank ON ws.word = freq_rank.word
                    WHERE ws.observation_count >= 2
                    ORDER BY ws.avg_speed_ms_per_letter ASC
                    LIMIT ?
                """,
                    (limit,),
                )
            rows = cursor.fetchall()
            return [
                WordStatisticsLite(
                    word=r[0],
                    avg_speed_ms_per_letter=r[1],
                    total_duration_ms=r[2],
                    total_letters=r[3],
                    rank=r[4],
                )
                for r in rows
            ]

    def delete_words_by_list(self, words: list[str]) -> int:
        """Delete word statistics for words in the given list."""
        if not words:
            return 0
        with self.get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ",".join("?" * len(words))
            cursor.execute(f"DELETE FROM word_statistics WHERE word IN ({placeholders})", words)
            conn.commit()
            return cursor.rowcount

    def clean_ignored_words_stats(self, is_ignored_callback: callable) -> int:
        """Delete word statistics for ignored words using hash check.

        Args:
            is_ignored_callback: Function that takes a plaintext word and returns True if ignored

        Returns:
            Number of rows deleted
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Get all words from word_statistics
            cursor.execute("SELECT word FROM word_statistics")
            words_to_check = [row[0] for row in cursor.fetchall()]

            # Filter to find ignored words
            ignored_words = [word for word in words_to_check if is_ignored_callback(word)]

            if ignored_words:
                # Build placeholders for IN clause
                placeholders = ','.join('?' * len(ignored_words))
                cursor.execute(
                    f"DELETE FROM word_statistics WHERE word IN ({placeholders})",
                    ignored_words
                )
                conn.commit()
                return cursor.rowcount

            return 0

    # ========== Ignored Words Operations ==========

    def add_ignored_word(self, word_hash: str, timestamp_ms: int) -> bool:
        """Add ignored word hash to database."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "INSERT INTO ignored_words (word_hash, added_at) VALUES (?, ?)",
                    (word_hash, timestamp_ms),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def is_word_ignored(self, word_hash: str) -> bool:
        """Check if word hash is in ignored list."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM ignored_words WHERE word_hash = ? LIMIT 1", (word_hash,))
            return cursor.fetchone() is not None

    def get_all_ignored_word_hashes(self) -> list[dict]:
        """Get all ignored word hashes for sync."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT word_hash, added_at FROM ignored_words")
            return [{"word_hash": row[0], "added_at": row[1]} for row in cursor.fetchall()]

    # ========== High Score Operations ==========

    def store_high_score(self, date: str, wpm: float, duration_ms: int, key_count: int) -> None:
        """Store a high score for a date."""
        timestamp_ms = int(time.time() * 1000)
        duration_sec = duration_ms / 1000.0
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO high_scores
                (date, fastest_burst_wpm, burst_duration_sec, burst_key_count, timestamp, burst_duration_ms)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (date, wpm, duration_sec, key_count, timestamp_ms, duration_ms),
            )
            conn.commit()

    def batch_insert_high_scores(self, records: list[dict]) -> int:
        """Batch insert high score records.

        Args:
            records: List of high score dictionaries

        Returns:
            Number of records actually inserted (excluding duplicates)
        """
        if not records:
            return 0

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Get count before insert
            cursor.execute("SELECT COUNT(*) FROM high_scores")
            before_count = cursor.fetchone()[0]

            # Prepare data tuples (excluding id - it's auto-incremented)
            data_tuples = []
            for r in records:
                data_tuples.append(
                    (
                        r.get("date"),
                        r.get("fastest_burst_wpm"),
                        r.get("burst_duration_sec"),
                        r.get("burst_key_count"),
                        r.get("timestamp"),
                        r.get("burst_duration_ms"),
                    )
                )

            # Use executemany with INSERT OR IGNORE to skip duplicates
            # With UNIQUE constraint on timestamp, duplicates will be ignored
            cursor.executemany(
                """
                INSERT OR IGNORE INTO high_scores
                (date, fastest_burst_wpm, burst_duration_sec,
                 burst_key_count, timestamp, burst_duration_ms)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                data_tuples,
            )

            conn.commit()

            # Get count after insert to determine actual inserted count
            cursor.execute("SELECT COUNT(*) FROM high_scores")
            after_count = cursor.fetchone()[0]

            return after_count - before_count

    def get_today_high_score(self, date: str) -> float | None:
        """Get today's highest WPM."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT MAX(fastest_burst_wpm) FROM high_scores WHERE date = ?
            """,
                (date,),
            )
            result = cursor.fetchone()
            return result[0] if result and result[0] else None

    def get_all_time_high_score(self) -> float | None:
        """Get all-time highest WPM."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT MAX(fastest_burst_wpm) FROM high_scores
            """,
            )
            result = cursor.fetchone()
            return result[0] if result and result[0] else None

    # ========== Daily Summary Operations ==========

    def update_daily_summary(
        self,
        date: str,
        total_keystrokes: int,
        total_bursts: int,
        avg_wpm: float,
        slowest_keycode: int,
        slowest_key_name: str,
        total_typing_sec: int,
    ) -> None:
        """Update daily summary."""
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO daily_summaries
                (date, total_keystrokes, total_bursts, avg_wpm,
                 slowest_keycode, slowest_key_name, total_typing_sec)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    date,
                    total_keystrokes,
                    total_bursts,
                    avg_wpm,
                    slowest_keycode,
                    slowest_key_name,
                    total_typing_sec,
                ),
            )
            conn.commit()

    def batch_insert_daily_summaries(self, records: list[dict]) -> int:
        """Batch insert daily summary records.

        Args:
            records: List of daily summary dictionaries

        Returns:
            Number of records actually inserted (excluding duplicates)
        """
        if not records:
            return 0

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Get count before insert
            cursor.execute("SELECT COUNT(*) FROM daily_summaries")
            before_count = cursor.fetchone()[0]

            # Prepare data tuples
            data_tuples = []
            for r in records:
                data_tuples.append(
                    (
                        r.get("date"),
                        r.get("total_keystrokes"),
                        r.get("total_bursts"),
                        r.get("avg_wpm"),
                        r.get("slowest_keycode"),
                        r.get("slowest_key_name"),
                        r.get("total_typing_sec"),
                    )
                )

            # Use executemany for efficient bulk insert
            cursor.executemany(
                """
                INSERT OR IGNORE INTO daily_summaries
                (date, total_keystrokes, total_bursts, avg_wpm,
                 slowest_keycode, slowest_key_name, total_typing_sec)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                data_tuples,
            )

            conn.commit()

            # Get count after insert to determine actual inserted count
            cursor.execute("SELECT COUNT(*) FROM daily_summaries")
            after_count = cursor.fetchone()[0]

            return after_count - before_count

    def get_daily_summary(self, date: str) -> DailySummaryDB | None:
        """Get daily summary for a date."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT total_keystrokes, total_bursts, avg_wpm,
                       slowest_keycode, slowest_key_name, total_typing_sec, summary_sent
                FROM daily_summaries WHERE date = ?
            """,
                (date,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return DailySummaryDB(
                total_keystrokes=row[0],
                total_bursts=row[1],
                avg_wpm=row[2],
                slowest_keycode=row[3],
                slowest_key_name=row[4],
                total_typing_sec=row[5],
                summary_sent=bool(row[6]),
            )

    def mark_summary_sent(self, date: str) -> None:
        """Mark daily summary as sent."""
        with self.get_connection() as conn:
            conn.execute(
                """
                UPDATE daily_summaries SET summary_sent = 1 WHERE date = ?
            """,
                (date,),
            )
            conn.commit()

    # ========== All-Time Statistics ==========

    def get_all_time_typing_time(self, exclude_today: str | None = None) -> int:
        """Get all-time total typing time."""
        if exclude_today:
            # Calculate today's time and subtract from cache
            start_of_day = int(datetime.strptime(exclude_today, "%Y-%m-%d").timestamp() * 1000)
            end_of_day = start_of_day + 86400000

            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT COALESCE(SUM(duration_ms), 0) FROM bursts
                    WHERE start_time >= ? AND start_time < ?
                """,
                    (start_of_day, end_of_day),
                )
                today_ms = cursor.fetchone()[0]
                return self._cache_all_time_typing_sec - int(today_ms / 1000)

        return self._cache_all_time_typing_sec

    def get_today_typing_time(self, date: str) -> int:
        """Get typing time for a specific date."""
        start_of_day = int(datetime.strptime(date, "%Y-%m-%d").timestamp() * 1000)
        end_of_day = start_of_day + 86400000

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COALESCE(SUM(duration_ms), 0) FROM bursts
                WHERE start_time >= ? AND start_time < ?
            """,
                (start_of_day, end_of_day),
            )
            return cursor.fetchone()[0]

    def get_all_time_keystrokes_and_bursts(
        self, exclude_today: str | None = None
    ) -> tuple[int, int]:
        """Get all-time total keystrokes and bursts."""
        if exclude_today:
            start_of_day = int(datetime.strptime(exclude_today, "%Y-%m-%d").timestamp() * 1000)
            end_of_day = start_of_day + 86400000

            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT COALESCE(SUM(net_key_count), 0),
                           COUNT(*)
                    FROM bursts
                    WHERE start_time >= ? AND start_time < ?
                """,
                    (start_of_day, end_of_day),
                )
                today_keystrokes, today_bursts = cursor.fetchone()
                return (
                    self._cache_all_time_keystrokes - int(today_keystrokes),
                    self._cache_all_time_bursts - int(today_bursts),
                )

        return (self._cache_all_time_keystrokes, self._cache_all_time_bursts)

    def get_average_burst_wpm(self) -> float | None:
        """Get long-term average WPM across all recorded bursts."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT AVG(avg_wpm) FROM bursts
                WHERE avg_wpm > 0
            """,
            )
            result = cursor.fetchone()
            return result[0] if result and result[0] else None

    def get_all_burst_wpms_ordered(self) -> list[float]:
        """Get all burst WPM values ordered by time."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT avg_wpm FROM bursts ORDER BY start_time")
            return [row[0] for row in cursor.fetchall() if row[0] is not None]

    # ========== Data Management ==========

    def delete_old_data(self, retention_days: int) -> None:
        """Delete data older than retention period."""
        if retention_days < 0:
            return

        cutoff_ms = int((datetime.now() - timedelta(days=retention_days)).timestamp() * 1000)
        cutoff_date = (datetime.now() - timedelta(days=retention_days)).strftime("%Y-%m-%d")
        with self.get_connection() as conn:
            conn.execute("DELETE FROM bursts WHERE start_time < ?", (cutoff_ms,))
            conn.execute("DELETE FROM daily_summaries WHERE date < ?", (cutoff_date,))
            conn.commit()

    def clear_database(self) -> None:
        """Clear all data from database."""
        with self.get_connection() as conn:
            conn.execute("DELETE FROM bursts")
            conn.execute("DELETE FROM statistics")
            conn.execute("DELETE FROM high_scores")
            conn.execute("DELETE FROM daily_summaries")
            conn.execute("DELETE FROM word_statistics")
            conn.execute("DELETE FROM settings WHERE key LIKE 'last_processed_event_id_%'")
            conn.commit()

    def export_to_csv(self, file_path, start_date: str) -> int:
        """Export data to CSV file."""
        count = 0
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Get all bursts
            cursor.execute("SELECT * FROM bursts")
            rows = cursor.fetchall()

            # Get column names
            cursor.execute("PRAGMA table_info(bursts)")
            columns = [col[1] for col in cursor.fetchall()]

            with open(file_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(columns)
                writer.writerows(rows)
                count = len(rows)

        return count
