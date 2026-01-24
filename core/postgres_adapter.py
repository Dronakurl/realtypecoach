"""PostgreSQL adapter for RealTypeCoach database operations."""

import csv
import logging
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

try:
    import psycopg2
    import psycopg2.extras
    from psycopg2 import pool
    from psycopg2.extensions import connection
except ImportError:
    psycopg2 = None

from core.database_adapter import AdapterError, ConnectionError, DatabaseAdapter
from core.models import (
    BurstTimeSeries,
    DailySummaryDB,
    KeyPerformance,
    TypingTimeDataPoint,
    WordStatisticsLite,
)

if TYPE_CHECKING:
    from core.data_encryption import DataEncryption

log = logging.getLogger("realtypecoach.postgres_adapter")

# Legacy user ID for existing data
LEGACY_USER_ID = "00000000-0000-0000-0000-000000000000"


class PostgreSQLAdapter(DatabaseAdapter):
    """PostgreSQL database adapter implementation.

    Uses psycopg2 for database connectivity with connection pooling
    and SSL/TLS support. Supports multi-user data isolation and
    client-side encryption.
    """

    def __init__(
        self,
        host: str,
        port: int,
        database: str,
        user: str,
        password: str,
        sslmode: str = "require",
        min_connections: int = 1,
        max_connections: int = 10,
        user_id: str | None = None,
        encryption_key: bytes | None = None,
    ):
        """Initialize PostgreSQL adapter.

        Args:
            host: Database host address
            port: Database port (default: 5432)
            database: Database name
            user: Database user
            password: Database password
            sslmode: SSL mode (disable, allow, prefer, require, verify-ca, verify-full)
            min_connections: Minimum number of connections in pool
            max_connections: Maximum number of connections in pool
            user_id: User UUID for multi-user data isolation
            encryption_key: 32-byte encryption key for client-side encryption
        """
        if psycopg2 is None:
            raise ImportError(
                "psycopg2 is not installed. Install it with: pip install psycopg2-binary"
            )

        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.sslmode = sslmode
        self.min_connections = min_connections
        self.max_connections = max_connections

        self._connection_pool: pool.SimpleConnectionPool | None = None

        # User and encryption settings
        self.user_id = user_id or LEGACY_USER_ID
        self.encryption_key = encryption_key
        self.encryption: DataEncryption | None = None

        if encryption_key:
            from core.data_encryption import DataEncryption

            self.encryption = DataEncryption(encryption_key)

        # Initialize cache for all-time statistics
        self._cache_all_time_typing_sec = 0
        self._cache_all_time_keystrokes = 0
        self._cache_all_time_bursts = 0

    def initialize(self) -> None:
        """Initialize database schema and perform migrations."""
        # Create connection pool
        try:
            self._connection_pool = pool.SimpleConnectionPool(
                minconn=self.min_connections,
                maxconn=self.max_connections,
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                sslmode=self.sslmode,
                connect_timeout=10,
            )
            log.info(f"Created PostgreSQL connection pool: {self.host}:{self.port}/{self.database}")
        except Exception as e:
            raise ConnectionError(f"Failed to create connection pool: {e}")

        # Test connection
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT version()")
                version = cursor.fetchone()[0]
                log.info(f"Connected to PostgreSQL: {version[:50]}...")
        except Exception as e:
            raise ConnectionError(f"Failed to connect to database: {e}")

        # Create tables
        with self.get_connection() as conn:
            self._create_bursts_table(conn)
            self._create_statistics_table(conn)
            self._create_high_scores_table(conn)
            self._create_daily_summaries_table(conn)
            self._create_word_statistics_table(conn)
            conn.commit()

        # Initialize cache
        self._refresh_all_time_cache()

    @contextmanager
    def get_connection(self):
        """Get a database connection from the connection pool."""
        if self._connection_pool is None:
            raise AdapterError("Adapter not initialized. Call initialize() first.")

        conn = self._connection_pool.getconn()
        try:
            yield conn
        finally:
            self._connection_pool.putconn(conn)

    def close(self) -> None:
        """Close all database connections and cleanup resources."""
        if self._connection_pool:
            self._connection_pool.closeall()
            log.info("PostgreSQL connection pool closed")

    # ========== Table Creation ==========

    def _create_bursts_table(self, conn: connection) -> None:
        """Create bursts table."""
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bursts (
                id SERIAL NOT NULL,
                user_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000',
                start_time BIGINT NOT NULL,
                end_time BIGINT NOT NULL,
                key_count INTEGER NOT NULL,
                duration_ms INTEGER NOT NULL,
                avg_wpm DOUBLE PRECISION,
                qualifies_for_high_score INTEGER DEFAULT 0,
                backspace_count INTEGER DEFAULT 0,
                net_key_count INTEGER DEFAULT 0,
                encrypted_data TEXT,
                PRIMARY KEY (id, user_id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bursts_start_time ON bursts(start_time)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bursts_user_id ON bursts(user_id)")

        # Migrate if columns don't exist
        self._migrate_table_if_needed(cursor, "bursts")

    def _create_statistics_table(self, conn: connection) -> None:
        """Create statistics table."""
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS statistics (
                keycode INTEGER NOT NULL,
                user_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000',
                key_name TEXT NOT NULL,
                layout TEXT NOT NULL,
                avg_press_time DOUBLE PRECISION,
                total_presses INTEGER,
                slowest_ms DOUBLE PRECISION,
                fastest_ms DOUBLE PRECISION,
                last_updated BIGINT,
                encrypted_data TEXT,
                PRIMARY KEY (keycode, layout, user_id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_statistics_user_id ON statistics(user_id)")

        # Migrate if columns don't exist
        self._migrate_table_if_needed(cursor, "statistics")

    def _create_high_scores_table(self, conn: connection) -> None:
        """Create high_scores table."""
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS high_scores (
                id SERIAL NOT NULL,
                user_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000',
                date TEXT NOT NULL,
                fastest_burst_wpm DOUBLE PRECISION,
                burst_duration_sec DOUBLE PRECISION,
                burst_key_count INTEGER,
                timestamp BIGINT NOT NULL,
                burst_duration_ms INTEGER,
                encrypted_data TEXT,
                PRIMARY KEY (id, user_id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_high_scores_user_id ON high_scores(user_id)")

        # Migrate if columns don't exist
        self._migrate_table_if_needed(cursor, "high_scores")

    def _create_daily_summaries_table(self, conn: connection) -> None:
        """Create daily_summaries table."""
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_summaries (
                date TEXT NOT NULL,
                user_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000',
                total_keystrokes INTEGER,
                total_bursts INTEGER,
                avg_wpm DOUBLE PRECISION,
                slowest_keycode INTEGER,
                slowest_key_name TEXT,
                total_typing_sec INTEGER,
                summary_sent INTEGER DEFAULT 0,
                encrypted_data TEXT,
                PRIMARY KEY (date, user_id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_summaries_user_id ON daily_summaries(user_id)")

        # Migrate if columns don't exist
        self._migrate_table_if_needed(cursor, "daily_summaries")

    def _create_word_statistics_table(self, conn: connection) -> None:
        """Create word_statistics table."""
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS word_statistics (
                word TEXT NOT NULL,
                layout TEXT NOT NULL,
                user_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000',
                avg_speed_ms_per_letter DOUBLE PRECISION NOT NULL,
                total_letters INTEGER NOT NULL,
                total_duration_ms INTEGER NOT NULL,
                observation_count INTEGER NOT NULL,
                last_seen BIGINT NOT NULL,
                backspace_count INTEGER DEFAULT 0,
                editing_time_ms INTEGER DEFAULT 0,
                encrypted_data TEXT,
                PRIMARY KEY (word, layout, user_id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_word_statistics_user_id ON word_statistics(user_id)")

        # Migrate if columns don't exist
        self._migrate_table_if_needed(cursor, "word_statistics")

        # Create users and sync_log tables
        self._create_users_table(conn)
        self._create_sync_log_table(conn)

    def _create_users_table(self, conn: connection) -> None:
        """Create users table."""
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                username TEXT NOT NULL UNIQUE,
                email TEXT UNIQUE,
                display_name TEXT,
                created_at BIGINT NOT NULL,
                last_sync BIGINT,
                is_active INTEGER DEFAULT 1,
                metadata TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")

    def _create_sync_log_table(self, conn: connection) -> None:
        """Create sync_log table."""
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_log (
                id SERIAL PRIMARY KEY,
                user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                sync_type TEXT NOT NULL,
                started_at BIGINT NOT NULL,
                completed_at BIGINT,
                records_pushed INTEGER DEFAULT 0,
                records_pulled INTEGER DEFAULT 0,
                conflicts_resolved INTEGER DEFAULT 0,
                status TEXT NOT NULL,
                error_message TEXT,
                metadata TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sync_log_user_id ON sync_log(user_id)")

    def _migrate_table_if_needed(self, cursor, table: str) -> None:
        """Migrate table to add user_id and encrypted_data columns if not present.

        Args:
            cursor: Database cursor
            table: Table name to check/migrate
        """
        # Check if user_id column exists
        cursor.execute(f"""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='{table}' AND column_name='user_id'
            )
        """)
        has_user_id = cursor.fetchone()[0]

        if not has_user_id:
            log.info(f"Migrating {table}: adding user_id and encrypted_data columns")
            self._migrate_table_add_columns(cursor, table)

    def _migrate_table_add_columns(self, cursor, table: str) -> None:
        """Add user_id and encrypted_data columns to existing table.

        Args:
            cursor: Database cursor
            table: Table name to migrate
        """
        # Add columns
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS user_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000'")
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS encrypted_data TEXT")

        # Create index on user_id
        cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_user_id ON {table}(user_id)")

        # Update primary key to include user_id
        # Note: This varies by table due to different primary keys
        if table == "bursts":
            cursor.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS bursts_pkey")
            cursor.execute(f"ALTER TABLE {table} ADD PRIMARY KEY (id, user_id)")
        elif table == "statistics":
            cursor.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS statistics_pkey")
            cursor.execute(f"ALTER TABLE {table} ADD PRIMARY KEY (keycode, layout, user_id)")
        elif table == "word_statistics":
            cursor.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS word_statistics_pkey")
            cursor.execute(f"ALTER TABLE {table} ADD PRIMARY KEY (word, layout, user_id)")
        elif table == "high_scores":
            cursor.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS high_scores_pkey")
            cursor.execute(f"ALTER TABLE {table} ADD PRIMARY KEY (id, user_id)")
        elif table == "daily_summaries":
            cursor.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS daily_summaries_pkey")
            cursor.execute(f"ALTER TABLE {table} ADD PRIMARY KEY (date, user_id)")

        log.info(f"Migration completed for table {table}")

    def _refresh_all_time_cache(self) -> None:
        """Refresh all-time statistics cache from database."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COALESCE(SUM(duration_ms), 0) FROM bursts WHERE user_id = %s",
                (self.user_id,)
            )
            total_ms = cursor.fetchone()[0]
            self._cache_all_time_typing_sec = int(total_ms / 1000)

            cursor.execute(
                "SELECT COALESCE(SUM(net_key_count), 0) FROM bursts WHERE user_id = %s",
                (self.user_id,)
            )
            self._cache_all_time_keystrokes = int(cursor.fetchone()[0])

            cursor.execute(
                "SELECT COUNT(*) FROM bursts WHERE user_id = %s",
                (self.user_id,)
            )
            self._cache_all_time_bursts = int(cursor.fetchone()[0])

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

            # If encryption is enabled, encrypt the data
            encrypted_data = None
            if self.encryption:
                encrypted_data = self.encryption.encrypt_burst(
                    start_time=start_time,
                    end_time=end_time,
                    key_count=key_count,
                    backspace_count=backspace_count,
                    net_key_count=net_key_count,
                    duration_ms=duration_ms,
                    avg_wpm=avg_wpm,
                    qualifies_for_high_score=qualifies_for_high_score,
                )

            cursor.execute(
                """
                INSERT INTO bursts
                (user_id, start_time, end_time, key_count, backspace_count, net_key_count,
                 duration_ms, avg_wpm, qualifies_for_high_score, encrypted_data)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
                (
                    self.user_id,
                    start_time,
                    end_time,
                    key_count,
                    backspace_count,
                    net_key_count,
                    duration_ms,
                    avg_wpm,
                    1 if qualifies_for_high_score else 0,
                    encrypted_data,
                ),
            )
            conn.commit()

        # Update cache
        self._cache_all_time_typing_sec += duration_ms // 1000
        self._cache_all_time_keystrokes += net_key_count
        self._cache_all_time_bursts += 1

    def get_bursts_for_timeseries(self, start_ms: int, end_ms: int) -> list[BurstTimeSeries]:
        """Get burst data for time-series graph."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT start_time, avg_wpm
                FROM bursts
                WHERE user_id = %s AND start_time >= %s AND start_time < %s
                ORDER BY start_time
            """,
                (self.user_id, start_ms, end_ms),
            )
            rows = cursor.fetchall()
            return [BurstTimeSeries(timestamp_ms=r[0], avg_wpm=r[1]) for r in rows]

    def get_burst_wpm_histogram(self, bin_count: int = 50) -> list[tuple[float, int]]:
        """Get burst WPM distribution as histogram data."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Get all WPM values for current user
            cursor.execute(
                "SELECT avg_wpm FROM bursts WHERE user_id = %s AND avg_wpm IS NOT NULL ORDER BY avg_wpm",
                (self.user_id,)
            )
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
                WHERE user_id = %s
                ORDER BY start_time DESC
                LIMIT %s
            """,
                (self.user_id, limit),
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

    def get_burst_duration_stats_ms(self) -> tuple[int, int, int]:
        """Get burst duration statistics across all bursts."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COALESCE(AVG(duration_ms), 0),
                       COALESCE(MIN(duration_ms), 0),
                       COALESCE(MAX(duration_ms), 0)
                FROM bursts
                WHERE user_id = %s
            """,
                (self.user_id,),
            )
            result = cursor.fetchone()
            if result and result[0]:
                return (int(result[0]), int(result[1]), int(result[2]))
            return (0, 0, 0)

    def get_burst_stats_for_date_range(self, start_ms: int, end_ms: int) -> tuple[int, int]:
        """Get burst statistics for a date range."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Calculate keystrokes from bursts (sum of net_key_count)
            cursor.execute(
                """
                SELECT COALESCE(SUM(net_key_count), 0) FROM bursts
                WHERE user_id = %s AND start_time >= %s AND start_time < %s
            """,
                (self.user_id, start_ms, end_ms),
            )
            total_keystrokes = cursor.fetchone()[0]

            # Count bursts
            cursor.execute(
                """
                SELECT COUNT(*) FROM bursts
                WHERE user_id = %s AND start_time >= %s AND start_time < %s
            """,
                (self.user_id, start_ms, end_ms),
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
                WHERE user_id = %s AND start_time >= %s AND duration_ms >= %s
                ORDER BY avg_wpm ASC
            """,
                (self.user_id, start_ms, min_duration_ms),
            )
            return [row[0] for row in cursor.fetchall()]

    def get_total_burst_duration(self, start_ms: int, end_ms: int) -> int:
        """Get total burst duration for a date range."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COALESCE(SUM(duration_ms), 0) FROM bursts
                WHERE user_id = %s AND start_time >= %s AND start_time < %s
            """,
                (self.user_id, start_ms, end_ms),
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
            group_by = "TO_TIMESTAMP(TO_CHAR(TO_TIMESTAMP(start_time / 1000.0), 'YYYY-MM-DD'), 'YYYY-MM-DD')"
            period_key_format = "TO_CHAR(TO_TIMESTAMP(start_time / 1000.0), 'YYYY-MM-DD')"
        elif granularity == "week":
            group_by = "TO_CHAR(TO_TIMESTAMP(start_time / 1000.0), 'IYYY-IW')"
            period_key_format = "TO_CHAR(TO_TIMESTAMP(start_time / 1000.0), 'IYYY-IW')"
        elif granularity == "month":
            group_by = "TO_CHAR(TO_TIMESTAMP(start_time / 1000.0), 'YYYY-MM')"
            period_key_format = "TO_CHAR(TO_TIMESTAMP(start_time / 1000.0), 'YYYY-MM')"
        elif granularity == "quarter":
            group_by = "TO_CHAR(TO_TIMESTAMP(start_time / 1000.0), 'YYYY-Q')"
            period_key_format = "TO_CHAR(TO_TIMESTAMP(start_time / 1000.0), 'YYYY-Q')"
        else:
            log.warning(f"Unknown granularity: {granularity}, defaulting to day")
            group_by = "TO_CHAR(TO_TIMESTAMP(start_time / 1000.0), 'YYYY-MM-DD')"
            period_key_format = "TO_CHAR(TO_TIMESTAMP(start_time / 1000.0), 'YYYY-MM-DD')"

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT
                    {period_key_format} AS period_key,
                    MIN(start_time) AS period_start_ms,
                    SUM(duration_ms) AS total_typing_ms,
                    COUNT(*) AS total_bursts,
                    AVG(avg_wpm) AS avg_wpm
                FROM bursts
                WHERE user_id = %s AND start_time >= %s AND start_time < %s
                GROUP BY period_key
                ORDER BY period_start_ms
                LIMIT %s
            """,
                (self.user_id, start_ms, end_ms, limit),
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
                if granularity == "week":
                    # period_key is YYYY-IW format, convert to YYYY-WWW
                    parts = period_key.split("-")
                    period_label = f"{parts[0]}-W{parts[1]}"
                elif granularity == "quarter":
                    # period_key is YYYY-Q format
                    period_label = period_key.upper()
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
                FROM statistics WHERE keycode = %s AND layout = %s AND user_id = %s
            """,
                (keycode, layout, self.user_id),
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
                        avg_press_time = %s, total_presses = %s, slowest_ms = %s,
                        fastest_ms = %s, last_updated = %s
                    WHERE keycode = %s AND layout = %s AND user_id = %s
                """,
                    (
                        new_avg,
                        new_total,
                        new_slowest,
                        new_fastest,
                        now_ms,
                        keycode,
                        layout,
                        self.user_id,
                    ),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO statistics
                    (keycode, key_name, layout, avg_press_time, total_presses,
                     slowest_ms, fastest_ms, last_updated, user_id)
                    VALUES (%s, %s, %s, %s, 1, %s, %s, %s, %s)
                """,
                    (
                        keycode,
                        key_name,
                        layout,
                        press_time_ms,
                        press_time_ms,
                        press_time_ms,
                        now_ms,
                        self.user_id,
                    ),
                )

            conn.commit()

    def get_slowest_keys(self, limit: int = 10, layout: str | None = None) -> list[KeyPerformance]:
        """Get slowest keys (highest average press time)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # PostgreSQL REGEXP using ~ operator
            letter_pattern = "^[a-z]$|(ä|ö|ü|ß)"

            if layout:
                cursor.execute(
                    """
                    SELECT s.keycode, s.key_name, s.avg_press_time, freq_rank.rank
                    FROM statistics s
                    INNER JOIN (
                        SELECT key_name, ROW_NUMBER() OVER (ORDER BY total_presses DESC) as rank
                        FROM statistics
                        WHERE layout = %s AND user_id = %s AND (key_name ~ %s)
                    ) freq_rank ON s.key_name = freq_rank.key_name
                    WHERE s.layout = %s AND s.user_id = %s AND s.total_presses >= 2
                        AND (s.key_name ~ %s)
                    ORDER BY s.avg_press_time DESC
                    LIMIT %s
                """,
                    (layout, self.user_id, letter_pattern, layout, self.user_id, letter_pattern, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT s.keycode, s.key_name, s.avg_press_time, freq_rank.rank
                    FROM statistics s
                    INNER JOIN (
                        SELECT key_name, ROW_NUMBER() OVER (ORDER BY total_presses DESC) as rank
                        FROM statistics
                        WHERE user_id = %s AND (key_name ~ %s)
                    ) freq_rank ON s.key_name = freq_rank.key_name
                    WHERE s.user_id = %s AND s.total_presses >= 2
                        AND (s.key_name ~ %s)
                    ORDER BY s.avg_press_time DESC
                    LIMIT %s
                """,
                    (self.user_id, letter_pattern, self.user_id, letter_pattern, limit),
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

            # PostgreSQL REGEXP using ~ operator
            letter_pattern = "^[a-z]$|(ä|ö|ü|ß)"

            if layout:
                cursor.execute(
                    """
                    SELECT s.keycode, s.key_name, s.avg_press_time, freq_rank.rank
                    FROM statistics s
                    INNER JOIN (
                        SELECT key_name, ROW_NUMBER() OVER (ORDER BY total_presses DESC) as rank
                        FROM statistics
                        WHERE layout = %s AND user_id = %s AND (key_name ~ %s)
                    ) freq_rank ON s.key_name = freq_rank.key_name
                    WHERE s.layout = %s AND s.user_id = %s AND s.total_presses >= 2
                        AND (s.key_name ~ %s)
                    ORDER BY s.avg_press_time ASC
                    LIMIT %s
                """,
                    (layout, self.user_id, letter_pattern, layout, self.user_id, letter_pattern, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT s.keycode, s.key_name, s.avg_press_time, freq_rank.rank
                    FROM statistics s
                    INNER JOIN (
                        SELECT key_name, ROW_NUMBER() OVER (ORDER BY total_presses DESC) as rank
                        FROM statistics
                        WHERE user_id = %s AND (key_name ~ %s)
                    ) freq_rank ON s.key_name = freq_rank.key_name
                    WHERE s.user_id = %s AND s.total_presses >= 2
                        AND (s.key_name ~ %s)
                    ORDER BY s.avg_press_time ASC
                    LIMIT %s
                """,
                    (self.user_id, letter_pattern, self.user_id, letter_pattern, limit),
                )
            rows = cursor.fetchall()
            return [
                KeyPerformance(keycode=r[0], key_name=r[1], avg_press_time=r[2], rank=r[3])
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
                WHERE word = %s AND layout = %s AND user_id = %s
            """,
                (word, layout, self.user_id),
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
                        avg_speed_ms_per_letter = %s,
                        total_letters = %s,
                        total_duration_ms = %s,
                        observation_count = %s,
                        last_seen = %s,
                        backspace_count = %s,
                        editing_time_ms = %s
                    WHERE word = %s AND layout = %s AND user_id = %s
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
                        self.user_id,
                    ),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO word_statistics
                    (word, layout, avg_speed_ms_per_letter, total_letters,
                     total_duration_ms, observation_count, last_seen,
                     backspace_count, editing_time_ms, user_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                        self.user_id,
                    ),
                )

            conn.commit()

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
                        WHERE layout = %s AND user_id = %s
                    ) freq_rank ON ws.word = freq_rank.word
                    WHERE ws.layout = %s AND ws.user_id = %s AND ws.observation_count >= 2
                    ORDER BY ws.avg_speed_ms_per_letter DESC
                    LIMIT %s
                """,
                    (layout, self.user_id, layout, self.user_id, limit),
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
                        WHERE user_id = %s
                    ) freq_rank ON ws.word = freq_rank.word
                    WHERE ws.user_id = %s AND ws.observation_count >= 2
                    ORDER BY ws.avg_speed_ms_per_letter DESC
                    LIMIT %s
                """,
                    (self.user_id, self.user_id, limit),
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
                        WHERE layout = %s AND user_id = %s
                    ) freq_rank ON ws.word = freq_rank.word
                    WHERE ws.layout = %s AND ws.user_id = %s AND ws.observation_count >= 2
                    ORDER BY ws.avg_speed_ms_per_letter ASC
                    LIMIT %s
                """,
                    (layout, self.user_id, layout, self.user_id, limit),
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
                        WHERE user_id = %s
                    ) freq_rank ON ws.word = freq_rank.word
                    WHERE ws.user_id = %s AND ws.observation_count >= 2
                    ORDER BY ws.avg_speed_ms_per_letter ASC
                    LIMIT %s
                """,
                    (self.user_id, self.user_id, limit),
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

    # ========== High Score Operations ==========

    def store_high_score(self, date: str, wpm: float, duration_ms: int, key_count: int) -> None:
        """Store a high score for a date."""
        timestamp_ms = int(time.time() * 1000)
        duration_sec = duration_ms / 1000.0
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Encrypt data if encryption is enabled
            encrypted_data = None
            if self.encryption:
                encrypted_data = self.encryption.encrypt_high_score(
                    date=date,
                    fastest_burst_wpm=wpm,
                    burst_duration_sec=duration_sec,
                    burst_key_count=key_count,
                    timestamp=timestamp_ms,
                    burst_duration_ms=duration_ms,
                )

            cursor.execute(
                """
                INSERT INTO high_scores
                (user_id, date, fastest_burst_wpm, burst_duration_sec, burst_key_count, timestamp, burst_duration_ms, encrypted_data)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
                (self.user_id, date, wpm, duration_sec, key_count, timestamp_ms, duration_ms, encrypted_data),
            )
            conn.commit()

    def get_today_high_score(self, date: str) -> float | None:
        """Get today's highest WPM."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT MAX(fastest_burst_wpm) FROM high_scores WHERE user_id = %s AND date = %s
            """,
                (self.user_id, date),
            )
            result = cursor.fetchone()
            return result[0] if result and result[0] else None

    def get_all_time_high_score(self) -> float | None:
        """Get all-time highest WPM."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT MAX(fastest_burst_wpm) FROM high_scores WHERE user_id = %s
            """,
                (self.user_id,),
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
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO daily_summaries
                (user_id, date, total_keystrokes, total_bursts, avg_wpm,
                 slowest_keycode, slowest_key_name, total_typing_sec)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, date) DO UPDATE SET
                    total_keystrokes = EXCLUDED.total_keystrokes,
                    total_bursts = EXCLUDED.total_bursts,
                    avg_wpm = EXCLUDED.avg_wpm,
                    slowest_keycode = EXCLUDED.slowest_keycode,
                    slowest_key_name = EXCLUDED.slowest_key_name,
                    total_typing_sec = EXCLUDED.total_typing_sec
            """,
                (
                    self.user_id,
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

    def get_daily_summary(self, date: str) -> DailySummaryDB | None:
        """Get daily summary for a date."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT total_keystrokes, total_bursts, avg_wpm,
                       slowest_keycode, slowest_key_name, total_typing_sec, summary_sent
                FROM daily_summaries WHERE user_id = %s AND date = %s
            """,
                (self.user_id, date),
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
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE daily_summaries SET summary_sent = 1 WHERE user_id = %s AND date = %s
            """,
                (self.user_id, date),
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
                    WHERE user_id = %s AND start_time >= %s AND start_time < %s
                """,
                    (self.user_id, start_of_day, end_of_day),
                )
                today_ms = cursor.fetchone()[0]
                return self._cache_all_time_typing_sec - int(today_ms / 1000)

        return self._cache_all_time_typing_sec

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
                    WHERE user_id = %s AND start_time >= %s AND start_time < %s
                """,
                    (self.user_id, start_of_day, end_of_day),
                )
                today_keystrokes, today_bursts = cursor.fetchone()
                return (
                    self._cache_all_time_keystrokes - int(today_keystrokes),
                    self._cache_all_time_bursts - int(today_bursts),
                )

        return (self._cache_all_time_keystrokes, self._cache_all_time_bursts)

    # ========== Data Management ==========

    def delete_old_data(self, retention_days: int) -> None:
        """Delete data older than retention period."""
        if retention_days < 0:
            return

        cutoff_ms = int((datetime.now() - timedelta(days=retention_days)).timestamp() * 1000)
        cutoff_date = (datetime.now() - timedelta(days=retention_days)).strftime("%Y-%m-%d")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM bursts WHERE user_id = %s AND start_time < %s", (self.user_id, cutoff_ms,))
            cursor.execute("DELETE FROM daily_summaries WHERE user_id = %s AND date < %s", (self.user_id, cutoff_date,))
            conn.commit()

    def clear_database(self) -> None:
        """Clear all data from database for current user."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM bursts WHERE user_id = %s", (self.user_id,))
            cursor.execute("DELETE FROM statistics WHERE user_id = %s", (self.user_id,))
            cursor.execute("DELETE FROM high_scores WHERE user_id = %s", (self.user_id,))
            cursor.execute("DELETE FROM daily_summaries WHERE user_id = %s", (self.user_id,))
            cursor.execute("DELETE FROM word_statistics WHERE user_id = %s", (self.user_id,))
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
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'bursts'
                ORDER BY ordinal_position
            """)
            columns = [col[0] for col in cursor.fetchall()]

            with open(file_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(columns)
                writer.writerows(rows)
                count = len(rows)

        return count
