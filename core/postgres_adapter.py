"""PostgreSQL adapter for RealTypeCoach database operations."""

import csv
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import List, Optional, Tuple
import logging

try:
    import psycopg2
    import psycopg2.extras
    from psycopg2 import pool
    from psycopg2.extensions import connection
except ImportError:
    psycopg2 = None

from core.database_adapter import DatabaseAdapter, AdapterError, ConnectionError, QueryError
from core.models import (
    DailySummaryDB,
    KeyPerformance,
    WordStatisticsLite,
    BurstTimeSeries,
    TypingTimeDataPoint,
)

log = logging.getLogger("realtypecoach.postgres_adapter")


class PostgreSQLAdapter(DatabaseAdapter):
    """PostgreSQL database adapter implementation.

    Uses psycopg2 for database connectivity with connection pooling
    and SSL/TLS support.
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
        """
        if psycopg2 is None:
            raise ImportError(
                "psycopg2 is not installed. "
                "Install it with: pip install psycopg2-binary"
            )

        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.sslmode = sslmode
        self.min_connections = min_connections
        self.max_connections = max_connections

        self._connection_pool: Optional[pool.SimpleConnectionPool] = None

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
                id SERIAL PRIMARY KEY,
                start_time BIGINT NOT NULL,
                end_time BIGINT NOT NULL,
                key_count INTEGER NOT NULL,
                duration_ms INTEGER NOT NULL,
                avg_wpm DOUBLE PRECISION,
                qualifies_for_high_score INTEGER DEFAULT 0,
                backspace_count INTEGER DEFAULT 0,
                net_key_count INTEGER DEFAULT 0
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_bursts_start_time ON bursts(start_time)"
        )

    def _create_statistics_table(self, conn: connection) -> None:
        """Create statistics table."""
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS statistics (
                keycode INTEGER NOT NULL,
                key_name TEXT NOT NULL,
                layout TEXT NOT NULL,
                avg_press_time DOUBLE PRECISION,
                total_presses INTEGER,
                slowest_ms DOUBLE PRECISION,
                fastest_ms DOUBLE PRECISION,
                last_updated BIGINT,
                PRIMARY KEY (keycode, layout)
            )
        """)

    def _create_high_scores_table(self, conn: connection) -> None:
        """Create high_scores table."""
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS high_scores (
                id SERIAL PRIMARY KEY,
                date TEXT NOT NULL,
                fastest_burst_wpm DOUBLE PRECISION,
                burst_duration_sec DOUBLE PRECISION,
                burst_key_count INTEGER,
                timestamp BIGINT NOT NULL,
                burst_duration_ms INTEGER
            )
        """)

    def _create_daily_summaries_table(self, conn: connection) -> None:
        """Create daily_summaries table."""
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_summaries (
                date TEXT PRIMARY KEY,
                total_keystrokes INTEGER,
                total_bursts INTEGER,
                avg_wpm DOUBLE PRECISION,
                slowest_keycode INTEGER,
                slowest_key_name TEXT,
                total_typing_sec INTEGER,
                summary_sent INTEGER DEFAULT 0
            )
        """)

    def _create_word_statistics_table(self, conn: connection) -> None:
        """Create word_statistics table."""
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS word_statistics (
                word TEXT NOT NULL,
                layout TEXT NOT NULL,
                avg_speed_ms_per_letter DOUBLE PRECISION NOT NULL,
                total_letters INTEGER NOT NULL,
                total_duration_ms INTEGER NOT NULL,
                observation_count INTEGER NOT NULL,
                last_seen BIGINT NOT NULL,
                backspace_count INTEGER DEFAULT 0,
                editing_time_ms INTEGER DEFAULT 0,
                PRIMARY KEY (word, layout)
            )
        """)

    def _refresh_all_time_cache(self) -> None:
        """Refresh all-time statistics cache from database."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COALESCE(SUM(duration_ms), 0) FROM bursts")
            total_ms = cursor.fetchone()[0]
            self._cache_all_time_typing_sec = int(total_ms / 1000)

            cursor.execute("SELECT COALESCE(SUM(net_key_count), 0) FROM bursts")
            self._cache_all_time_keystrokes = int(cursor.fetchone()[0])

            cursor.execute("SELECT COUNT(*) FROM bursts")
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
            cursor.execute(
                """
                INSERT INTO bursts
                (start_time, end_time, key_count, backspace_count, net_key_count,
                 duration_ms, avg_wpm, qualifies_for_high_score)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
                (
                    start_time,
                    end_time,
                    key_count,
                    backspace_count,
                    net_key_count,
                    duration_ms,
                    avg_wpm,
                    1 if qualifies_for_high_score else 0,
                ),
            )
            conn.commit()

        # Update cache
        self._cache_all_time_typing_sec += duration_ms // 1000
        self._cache_all_time_keystrokes += net_key_count
        self._cache_all_time_bursts += 1

    def get_bursts_for_timeseries(
        self, start_ms: int, end_ms: int
    ) -> List[BurstTimeSeries]:
        """Get burst data for time-series graph."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT start_time, avg_wpm
                FROM bursts
                WHERE start_time >= %s AND start_time < %s
                ORDER BY start_time
            """,
                (start_ms, end_ms),
            )
            rows = cursor.fetchall()
            return [BurstTimeSeries(timestamp_ms=r[0], avg_wpm=r[1]) for r in rows]

    def get_burst_wpm_histogram(self, bin_count: int = 50) -> List[Tuple[float, int]]:
        """Get burst WPM distribution as histogram data."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Get all WPM values
            cursor.execute(
                "SELECT avg_wpm FROM bursts WHERE avg_wpm IS NOT NULL ORDER BY avg_wpm"
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
                (center, count) for center, count in zip(bin_centers, bins) if count > 0
            ]

    def get_recent_bursts(
        self, limit: int = 3
    ) -> List[Tuple[int, float, int, int, int, int, str]]:
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
                LIMIT %s
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

    def get_burst_duration_stats_ms(self) -> Tuple[int, int, int]:
        """Get burst duration statistics across all bursts."""
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
                return (int(result[0]), int(result[1]), int(result[2]))
            return (0, 0, 0)

    def get_burst_stats_for_date_range(
        self, start_ms: int, end_ms: int
    ) -> Tuple[int, int]:
        """Get burst statistics for a date range."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Calculate keystrokes from bursts (sum of net_key_count)
            cursor.execute(
                """
                SELECT COALESCE(SUM(net_key_count), 0) FROM bursts
                WHERE start_time >= %s AND start_time < %s
            """,
                (start_ms, end_ms),
            )
            total_keystrokes = cursor.fetchone()[0]

            # Count bursts
            cursor.execute(
                """
                SELECT COUNT(*) FROM bursts
                WHERE start_time >= %s AND start_time < %s
            """,
                (start_ms, end_ms),
            )
            total_bursts = cursor.fetchone()[0]

            return (total_keystrokes, total_bursts)

    def get_burst_wpms_for_threshold(
        self, start_ms: int, min_duration_ms: int
    ) -> List[float]:
        """Get burst WPMS for threshold calculation."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT avg_wpm FROM bursts
                WHERE start_time >= %s AND duration_ms >= %s
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
                WHERE start_time >= %s AND start_time < %s
            """,
                (start_ms, end_ms),
            )
            return cursor.fetchone()[0]

    def get_typing_time_by_granularity(
        self,
        granularity: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 90,
    ) -> List[TypingTimeDataPoint]:
        """Get typing time aggregated by time granularity."""
        # Calculate date range
        if end_date:
            end_ms = int(
                (
                    datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
                ).timestamp()
                * 1000
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
                WHERE start_time >= %s AND start_time < %s
                GROUP BY period_key
                ORDER BY period_start_ms
                LIMIT %s
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
                FROM statistics WHERE keycode = %s AND layout = %s
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
                        avg_press_time = %s, total_presses = %s, slowest_ms = %s,
                        fastest_ms = %s, last_updated = %s
                    WHERE keycode = %s AND layout = %s
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
                    VALUES (%s, %s, %s, %s, 1, %s, %s, %s)
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

    def get_slowest_keys(
        self, limit: int = 10, layout: Optional[str] = None
    ) -> List[KeyPerformance]:
        """Get slowest keys (highest average press time)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # PostgreSQL REGEXP using ~ operator
            letter_pattern = "^[a-z]$|(ä|ö|ü|ß)"

            if layout:
                cursor.execute(
                    f"""
                    SELECT s.keycode, s.key_name, s.avg_press_time, freq_rank.rank
                    FROM statistics s
                    INNER JOIN (
                        SELECT key_name, ROW_NUMBER() OVER (ORDER BY total_presses DESC) as rank
                        FROM statistics
                        WHERE layout = %s AND (key_name ~ %s)
                    ) freq_rank ON s.key_name = freq_rank.key_name
                    WHERE s.layout = %s AND s.total_presses >= 2
                        AND (s.key_name ~ %s)
                    ORDER BY s.avg_press_time DESC
                    LIMIT %s
                """,
                    (layout, letter_pattern, layout, letter_pattern, limit),
                )
            else:
                cursor.execute(
                    f"""
                    SELECT s.keycode, s.key_name, s.avg_press_time, freq_rank.rank
                    FROM statistics s
                    INNER JOIN (
                        SELECT key_name, ROW_NUMBER() OVER (ORDER BY total_presses DESC) as rank
                        FROM statistics
                        WHERE (key_name ~ %s)
                    ) freq_rank ON s.key_name = freq_rank.key_name
                    WHERE s.total_presses >= 2
                        AND (s.key_name ~ %s)
                    ORDER BY s.avg_press_time DESC
                    LIMIT %s
                """,
                    (letter_pattern, letter_pattern, limit),
                )
            rows = cursor.fetchall()
            return [
                KeyPerformance(
                    keycode=r[0], key_name=r[1], avg_press_time=r[2], rank=r[3]
                )
                for r in rows
            ]

    def get_fastest_keys(
        self, limit: int = 10, layout: Optional[str] = None
    ) -> List[KeyPerformance]:
        """Get fastest keys (lowest average press time)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # PostgreSQL REGEXP using ~ operator
            letter_pattern = "^[a-z]$|(ä|ö|ü|ß)"

            if layout:
                cursor.execute(
                    f"""
                    SELECT s.keycode, s.key_name, s.avg_press_time, freq_rank.rank
                    FROM statistics s
                    INNER JOIN (
                        SELECT key_name, ROW_NUMBER() OVER (ORDER BY total_presses DESC) as rank
                        FROM statistics
                        WHERE layout = %s AND (key_name ~ %s)
                    ) freq_rank ON s.key_name = freq_rank.key_name
                    WHERE s.layout = %s AND s.total_presses >= 2
                        AND (s.key_name ~ %s)
                    ORDER BY s.avg_press_time ASC
                    LIMIT %s
                """,
                    (layout, letter_pattern, layout, letter_pattern, limit),
                )
            else:
                cursor.execute(
                    f"""
                    SELECT s.keycode, s.key_name, s.avg_press_time, freq_rank.rank
                    FROM statistics s
                    INNER JOIN (
                        SELECT key_name, ROW_NUMBER() OVER (ORDER BY total_presses DESC) as rank
                        FROM statistics
                        WHERE (key_name ~ %s)
                    ) freq_rank ON s.key_name = freq_rank.key_name
                    WHERE s.total_presses >= 2
                        AND (s.key_name ~ %s)
                    ORDER BY s.avg_press_time ASC
                    LIMIT %s
                """,
                    (letter_pattern, letter_pattern, limit),
                )
            rows = cursor.fetchall()
            return [
                KeyPerformance(
                    keycode=r[0], key_name=r[1], avg_press_time=r[2], rank=r[3]
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
                WHERE word = %s AND layout = %s
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
                        avg_speed_ms_per_letter = %s,
                        total_letters = %s,
                        total_duration_ms = %s,
                        observation_count = %s,
                        last_seen = %s,
                        backspace_count = %s,
                        editing_time_ms = %s
                    WHERE word = %s AND layout = %s
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
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
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

    def get_slowest_words(
        self, limit: int = 10, layout: Optional[str] = None
    ) -> List[WordStatisticsLite]:
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
                        WHERE layout = %s
                    ) freq_rank ON ws.word = freq_rank.word
                    WHERE ws.layout = %s AND ws.observation_count >= 2
                    ORDER BY ws.avg_speed_ms_per_letter DESC
                    LIMIT %s
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
                    LIMIT %s
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
        self, limit: int = 10, layout: Optional[str] = None
    ) -> List[WordStatisticsLite]:
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
                        WHERE layout = %s
                    ) freq_rank ON ws.word = freq_rank.word
                    WHERE ws.layout = %s AND ws.observation_count >= 2
                    ORDER BY ws.avg_speed_ms_per_letter ASC
                    LIMIT %s
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
                    LIMIT %s
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

    # ========== High Score Operations ==========

    def store_high_score(
        self, date: str, wpm: float, duration_ms: int, key_count: int
    ) -> None:
        """Store a high score for a date."""
        timestamp_ms = int(time.time() * 1000)
        duration_sec = duration_ms / 1000.0
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO high_scores
                (date, fastest_burst_wpm, burst_duration_sec, burst_key_count, timestamp, burst_duration_ms)
                VALUES (%s, %s, %s, %s, %s, %s)
            """,
                (date, wpm, duration_sec, key_count, timestamp_ms, duration_ms),
            )
            conn.commit()

    def get_today_high_score(self, date: str) -> Optional[float]:
        """Get today's highest WPM."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT MAX(fastest_burst_wpm) FROM high_scores WHERE date = %s
            """,
                (date,),
            )
            result = cursor.fetchone()
            return result[0] if result and result[0] else None

    def get_all_time_high_score(self) -> Optional[float]:
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
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO daily_summaries
                (date, total_keystrokes, total_bursts, avg_wpm,
                 slowest_keycode, slowest_key_name, total_typing_sec)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (date) DO UPDATE SET
                    total_keystrokes = EXCLUDED.total_keystrokes,
                    total_bursts = EXCLUDED.total_bursts,
                    avg_wpm = EXCLUDED.avg_wpm,
                    slowest_keycode = EXCLUDED.slowest_keycode,
                    slowest_key_name = EXCLUDED.slowest_key_name,
                    total_typing_sec = EXCLUDED.total_typing_sec
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

    def get_daily_summary(self, date: str) -> Optional[DailySummaryDB]:
        """Get daily summary for a date."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT total_keystrokes, total_bursts, avg_wpm,
                       slowest_keycode, slowest_key_name, total_typing_sec, summary_sent
                FROM daily_summaries WHERE date = %s
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
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE daily_summaries SET summary_sent = 1 WHERE date = %s
            """,
                (date,),
            )
            conn.commit()

    # ========== All-Time Statistics ==========

    def get_all_time_typing_time(self, exclude_today: Optional[str] = None) -> int:
        """Get all-time total typing time."""
        if exclude_today:
            # Calculate today's time and subtract from cache
            start_of_day = int(
                datetime.strptime(exclude_today, "%Y-%m-%d").timestamp() * 1000
            )
            end_of_day = start_of_day + 86400000

            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT COALESCE(SUM(duration_ms), 0) FROM bursts
                    WHERE start_time >= %s AND start_time < %s
                """,
                    (start_of_day, end_of_day),
                )
                today_ms = cursor.fetchone()[0]
                return self._cache_all_time_typing_sec - int(today_ms / 1000)

        return self._cache_all_time_typing_sec

    def get_all_time_keystrokes_and_bursts(
        self, exclude_today: Optional[str] = None
    ) -> Tuple[int, int]:
        """Get all-time total keystrokes and bursts."""
        if exclude_today:
            start_of_day = int(
                datetime.strptime(exclude_today, "%Y-%m-%d").timestamp() * 1000
            )
            end_of_day = start_of_day + 86400000

            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT COALESCE(SUM(net_key_count), 0),
                           COUNT(*)
                    FROM bursts
                    WHERE start_time >= %s AND start_time < %s
                """,
                    (start_of_day, end_of_day),
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

        cutoff_ms = int(
            (datetime.now() - timedelta(days=retention_days)).timestamp() * 1000
        )
        cutoff_date = (datetime.now() - timedelta(days=retention_days)).strftime(
            "%Y-%m-%d"
        )
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM bursts WHERE start_time < %s", (cutoff_ms,))
            cursor.execute("DELETE FROM daily_summaries WHERE date < %s", (cutoff_date,))
            conn.commit()

    def clear_database(self) -> None:
        """Clear all data from database."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM bursts")
            cursor.execute("DELETE FROM statistics")
            cursor.execute("DELETE FROM high_scores")
            cursor.execute("DELETE FROM daily_summaries")
            cursor.execute("DELETE FROM word_statistics")
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
