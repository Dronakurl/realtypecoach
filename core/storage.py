"""Storage management for RealTypeCoach - SQLite database operations."""

import csv
import re
import sqlite3
import time
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timedelta
import logging

from core.dictionary import Dictionary
from core.dictionary_config import DictionaryConfig
from core.word_detector import WordDetector
from core.models import (
    DailySummaryDB,
    KeyPerformance,
    WordStatisticsLite,
    BurstTimeSeries,
    WordInfo,
    TypingTimeDataPoint,
)
from utils.keycodes import is_letter_key
from utils.config import Config

log = logging.getLogger("realtypecoach.storage")


class Storage:
    """Database storage for typing data."""

    def __init__(
        self,
        db_path: Path,
        config: Config,
        word_boundary_timeout_ms: int = 1000,
        dictionary_config: Optional[DictionaryConfig] = None,
    ):
        """Initialize storage with database at given path.

        Args:
            db_path: Path to SQLite database file
            config: Config instance for accessing settings (required)
            word_boundary_timeout_ms: Max pause between letters before word splits (ms)
            dictionary_config: Dictionary configuration object

        Raises:
            ValueError: If word_boundary_timeout_ms is not positive or config is None
        """
        if word_boundary_timeout_ms <= 0:
            raise ValueError("word_boundary_timeout_ms must be positive")
        if config is None:
            raise ValueError("config parameter is required")
        self.db_path = db_path
        self.word_boundary_timeout_ms = word_boundary_timeout_ms
        self.config = config
        self._init_database()

        # Initialize dictionary with config (use default if not provided)
        dict_config = dictionary_config or DictionaryConfig()
        self.dictionary = Dictionary(dict_config)
        self.word_detector = WordDetector(
            word_boundary_timeout_ms=word_boundary_timeout_ms, min_word_length=3
        )

        self._add_word_statistics_columns()

    def _get_connection(self) -> sqlite3.Connection:
        """Create a database connection with REGEXP function enabled."""
        conn = sqlite3.connect(self.db_path)

        def regexp(expr, item):
            return re.search(expr, item) is not None if item else False

        conn.create_function("REGEXP", 2, regexp)
        return conn

    def _init_database(self) -> None:
        """Create all database tables if they don't exist."""
        with self._get_connection() as conn:
            self._create_key_events_table(conn)
            self._create_bursts_table(conn)
            self._create_statistics_table(conn)
            self._create_high_scores_table(conn)
            self._create_daily_summaries_table(conn)
            # Settings table is owned by Config class, not Storage
            self._create_word_statistics_table(conn)
            self._migrate_high_scores_duration_ms(conn)
            self._migrate_key_events_event_type(conn)
            conn.commit()

    def _create_key_events_table(self, conn: sqlite3.Connection) -> None:
        """Create key_events table."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS key_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keycode INTEGER NOT NULL,
                key_name TEXT NOT NULL,
                timestamp_ms INTEGER NOT NULL,
                event_type TEXT NOT NULL DEFAULT 'press'
            )
        """)

    def _create_bursts_table(self, conn: sqlite3.Connection) -> None:
        """Create bursts table."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bursts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_time INTEGER NOT NULL,
                end_time INTEGER NOT NULL,
                key_count INTEGER NOT NULL,
                duration_ms INTEGER NOT NULL,
                avg_wpm REAL,
                qualifies_for_high_score INTEGER DEFAULT 0
            )
        """)
        # Create index on start_time for faster time-series queries
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bursts_start_time ON bursts(start_time)"
        )

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

    def _create_high_scores_table(self, conn: sqlite3.Connection) -> None:
        """Create high_scores table."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS high_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                fastest_burst_wpm REAL,
                burst_duration_sec REAL,
                burst_key_count INTEGER,
                timestamp INTEGER NOT NULL,
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

    def _add_word_statistics_columns(self) -> None:
        """Add new columns to word_statistics table if they don't exist.

        Migration: Add backspace_count and editing_time_ms columns.
        """
        with self._get_connection() as conn:
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

    def _migrate_key_events_event_type(self, conn: sqlite3.Connection) -> None:
        """Migrate key_events table to add event_type column."""
        cursor = conn.cursor()

        # Check if event_type column exists
        cursor.execute("""
            SELECT COUNT(*) FROM pragma_table_info('key_events')
            WHERE name='event_type'
        """)
        has_column = cursor.fetchone()[0] > 0

        if not has_column:
            # Add new column
            cursor.execute("""
                ALTER TABLE key_events ADD COLUMN event_type TEXT NOT NULL DEFAULT 'press'
            """)
            log.info("Added event_type column to key_events table")

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

    def store_key_event(self, keycode: int, key_name: str, timestamp_ms: int) -> None:
        """Store a single key event.

        Args:
            keycode: Linux evdev keycode
            key_name: Human-readable key name
            timestamp_ms: Milliseconds since epoch
        """
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO key_events
                (keycode, key_name, timestamp_ms, event_type)
                VALUES (?, ?, ?, ?)
            """,
                (keycode, key_name, timestamp_ms, 'press'),
            )
            conn.commit()

    def store_burst(
        self,
        start_time: int,
        end_time: int,
        key_count: int,
        duration_ms: int,
        avg_wpm: float,
        qualifies_for_high_score: bool,
    ) -> None:
        """Store a burst.

        Args:
            start_time: Start timestamp (ms since epoch)
            end_time: End timestamp (ms since epoch)
            key_count: Number of keystrokes
            duration_ms: Burst duration in milliseconds
            avg_wpm: Average WPM during burst
            qualifies_for_high_score: Whether burst meets minimum duration
        """
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO bursts
                (start_time, end_time, key_count, duration_ms, avg_wpm, qualifies_for_high_score)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    start_time,
                    end_time,
                    key_count,
                    duration_ms,
                    avg_wpm,
                    int(qualifies_for_high_score),
                ),
            )
            conn.commit()

    def update_key_statistics(
        self, keycode: int, key_name: str, layout: str, press_time_ms: float
    ) -> None:
        """Update statistics for a key.

        Args:
            keycode: Linux evdev keycode
            key_name: Human-readable key name
            layout: Keyboard layout identifier
            press_time_ms: Time since last press
        """
        with self._get_connection() as conn:
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

    def store_high_score(
        self, date: str, wpm: float, duration_ms: int, key_count: int
    ) -> None:
        """Store a high score for a date.

        Args:
            date: Date string (YYYY-MM-DD)
            wpm: Words per minute achieved
            duration_ms: Burst duration in milliseconds
            key_count: Number of keystrokes
        """
        timestamp_ms = int(time.time() * 1000)
        duration_sec = duration_ms / 1000.0
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO high_scores
                (date, fastest_burst_wpm, burst_duration_sec, burst_key_count, timestamp, burst_duration_ms)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (date, wpm, duration_sec, key_count, timestamp_ms, duration_ms),
            )
            conn.commit()

    def get_today_high_score(self, date: str) -> Optional[float]:
        """Get today's highest WPM.

        Args:
            date: Date string (YYYY-MM-DD)

        Returns:
            WPM or None if no bursts today
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT MAX(fastest_burst_wpm) FROM high_scores WHERE date = ?
            """,
                (date,),
            )
            result = cursor.fetchone()
            return result[0] if result and result[0] else None

    def get_all_time_high_score(self) -> Optional[float]:
        """Get all-time highest WPM.

        Returns:
            WPM or None if no bursts recorded
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT MAX(fastest_burst_wpm) FROM high_scores
            """,
            )
            result = cursor.fetchone()
            return result[0] if result and result[0] else None

    def get_all_time_typing_time(self) -> int:
        """Get all-time total typing time.

        Returns:
            Total typing time in seconds
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COALESCE(SUM(total_typing_sec), 0) FROM daily_summaries
            """,
            )
            result = cursor.fetchone()
            return result[0] if result else 0

    def get_all_time_keystrokes_and_bursts(self) -> tuple[int, int]:
        """Get all-time total keystrokes and bursts.

        Returns:
            Tuple of (total_keystrokes, total_bursts) from daily_summaries table
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COALESCE(SUM(total_keystrokes), 0),
                       COALESCE(SUM(total_bursts), 0)
                FROM daily_summaries
            """,
            )
            result = cursor.fetchone()
            return (result[0], result[1]) if result else (0, 0)

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
        """Update daily summary.

        Args:
            date: Date string (YYYY-MM-DD)
            total_keystrokes: Total keystrokes today
            total_bursts: Total bursts today
            avg_wpm: Average WPM today
            slowest_keycode: Slowest keycode today
            slowest_key_name: Slowest key name today
            total_typing_sec: Total typing time today (seconds)
        """
        with self._get_connection() as conn:
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

    def get_slowest_keys(
        self, limit: int = 10, layout: Optional[str] = None
    ) -> List[KeyPerformance]:
        """Get slowest keys (highest average press time).

        Only includes letter keys (a-z, ä, ö, ü, ß).

        Args:
            limit: Maximum number of keys to return
            layout: Filter by layout (None for all layouts)

        Returns:
            List of KeyPerformance models
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if layout:
                cursor.execute(
                    """
                    SELECT keycode, key_name, avg_press_time
                    FROM statistics
                    WHERE layout = ? AND total_presses >= 2
                        AND (key_name REGEXP '^[a-z]$' OR key_name IN ('ä', 'ö', 'ü', 'ß'))
                    ORDER BY avg_press_time DESC
                    LIMIT ?
                """,
                    (layout, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT keycode, key_name, avg_press_time
                    FROM statistics
                    WHERE total_presses >= 2
                        AND (key_name REGEXP '^[a-z]$' OR key_name IN ('ä', 'ö', 'ü', 'ß'))
                    ORDER BY avg_press_time DESC
                    LIMIT ?
                """,
                    (limit,),
                )
            rows = cursor.fetchall()
            return [
                KeyPerformance(keycode=r[0], key_name=r[1], avg_press_time=r[2])
                for r in rows
            ]

    def get_fastest_keys(
        self, limit: int = 10, layout: Optional[str] = None
    ) -> List[KeyPerformance]:
        """Get fastest keys (lowest average press time).

        Only includes letter keys (a-z, ä, ö, ü, ß).

        Args:
            limit: Maximum number of keys to return
            layout: Filter by layout (None for all layouts)

        Returns:
            List of KeyPerformance models
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if layout:
                cursor.execute(
                    """
                    SELECT keycode, key_name, avg_press_time
                    FROM statistics
                    WHERE layout = ? AND total_presses >= 2
                        AND (key_name REGEXP '^[a-z]$' OR key_name IN ('ä', 'ö', 'ü', 'ß'))
                    ORDER BY avg_press_time ASC
                    LIMIT ?
                """,
                    (layout, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT keycode, key_name, avg_press_time
                    FROM statistics
                    WHERE total_presses >= 2
                        AND (key_name REGEXP '^[a-z]$' OR key_name IN ('ä', 'ö', 'ü', 'ß'))
                    ORDER BY avg_press_time ASC
                    LIMIT ?
                """,
                    (limit,),
                )
            rows = cursor.fetchall()
            return [
                KeyPerformance(keycode=r[0], key_name=r[1], avg_press_time=r[2])
                for r in rows
            ]

    def get_daily_summary(self, date: str) -> Optional[DailySummaryDB]:
        """Get daily summary for a date.

        Args:
            date: Date string (YYYY-MM-DD)

        Returns:
            DailySummaryDB model or None if not found
        """
        with self._get_connection() as conn:
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
        """Mark daily summary as sent.

        Args:
            date: Date string (YYYY-MM-DD)
        """
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE daily_summaries SET summary_sent = 1 WHERE date = ?
            """,
                (date,),
            )
            conn.commit()

    def export_to_csv(
        self,
        csv_path: Path,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> int:
        """Export key events to CSV file.

        Args:
            csv_path: Path to save CSV file
            start_date: Start date string (YYYY-MM-DD) or None
            end_date: End date string (YYYY-MM-DD) or None

        Returns:
            Number of rows exported
        """
        query = """
            SELECT timestamp_ms, keycode, key_name
            FROM key_events
        """
        params = []

        if start_date:
            start_ms = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
            query += " WHERE timestamp_ms >= ?"
            params.append(start_ms)

        if end_date:
            end_ms = int(
                (
                    datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
                ).timestamp()
                * 1000
            )
            if start_date:
                query += " AND timestamp_ms < ?"
            else:
                query += " WHERE timestamp_ms < ?"
            params.append(end_ms)

        query += " ORDER BY timestamp_ms"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()

            with open(csv_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp_ms", "keycode", "key_name"])
                writer.writerows(rows)

            return len(rows)

    def delete_old_data(self, retention_days: int) -> None:
        """Delete data older than retention period.

        Args:
            retention_days: Number of days to keep, or -1 to keep forever
        """
        if retention_days < 0:
            return

        cutoff_ms = int(
            (datetime.now() - timedelta(days=retention_days)).timestamp() * 1000
        )
        cutoff_date = (datetime.now() - timedelta(days=retention_days)).strftime(
            "%Y-%m-%d"
        )
        with self._get_connection() as conn:
            conn.execute("DELETE FROM key_events WHERE timestamp_ms < ?", (cutoff_ms,))
            conn.execute("DELETE FROM bursts WHERE start_time < ?", (cutoff_ms,))
            conn.execute("DELETE FROM daily_summaries WHERE date < ?", (cutoff_date,))
            conn.commit()

    def clear_database(self) -> None:
        """Clear all data from database."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM key_events")
            conn.execute("DELETE FROM bursts")
            conn.execute("DELETE FROM statistics")
            conn.execute("DELETE FROM high_scores")
            conn.execute("DELETE FROM daily_summaries")
            conn.execute("DELETE FROM word_statistics")
            conn.execute(
                "DELETE FROM settings WHERE key = ? OR key = ?",
                ("last_processed_event_id_us", "last_processed_event_id_de"),
            )
            conn.commit()

    def update_word_statistics(
        self,
        word: str,
        layout: str,
        duration_ms: int,
        num_letters: int,
        backspace_count: int = 0,
        editing_time_ms: int = 0,
    ) -> None:
        """Update statistics for a word with running average.

        Args:
            word: The word that was typed
            layout: Keyboard layout identifier
            duration_ms: Time taken to type the word (ms)
            num_letters: Number of letters in the word
            backspace_count: Number of backspaces used for this word
            editing_time_ms: Time spent editing with backspace (ms)
        """
        speed_per_letter = duration_ms / num_letters
        now_ms = int(time.time() * 1000)

        with self._get_connection() as conn:
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

    def _get_last_processed_event_id(self, layout: str) -> int:
        """Get the last processed event ID for a layout.

        Args:
            layout: Keyboard layout identifier

        Returns:
            Last processed event ID, or 0 if none
        """
        key = f"last_processed_event_id_{layout}"
        return self.config.get_int(key, 0)

    def _set_last_processed_event_id(self, layout: str, event_id: int) -> None:
        """Set the last processed event ID for a layout.

        Args:
            layout: Keyboard layout identifier
            event_id: Event ID to save
        """
        key = f"last_processed_event_id_{layout}"
        self.config.set(key, event_id)

    def _process_new_key_events(
        self, layout: str = "us", max_events: int = 1000
    ) -> int:
        """Process new key events to detect and update word statistics.

        Uses WordDetector to track backspace editing and validates words
        against dictionary. Only stores valid dictionary words.

        Args:
            layout: Keyboard layout identifier
            max_events: Maximum number of events to process in one call

        Returns:
            Number of events processed
        """
        # In accept_all mode, always process words
        # In validate mode, only process if at least one dictionary loaded
        if not self.dictionary.accept_all_mode and not self.dictionary.is_loaded():
            log.warning(
                "No dictionary loaded and accept_all_mode is False, skipping word processing"
            )
            return 0

        last_processed_id = self._get_last_processed_event_id(layout)

        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT id, key_name, timestamp_ms
                FROM key_events
                WHERE id > ?
                ORDER BY id
                LIMIT ?
            """,
                (last_processed_id, max_events),
            )

            events = cursor.fetchall()

            if not events:
                return 0

            last_event_id = last_processed_id

            for event_id, key_name, timestamp_ms in events:
                last_event_id = event_id

                is_letter = is_letter_key(key_name)
                word_info = self.word_detector.process_keystroke(
                    key_name, timestamp_ms, layout, is_letter
                )

                if word_info:
                    word = word_info.word

                    if self.dictionary.is_valid_word(
                        word, self._get_language_from_layout(layout)
                    ):
                        self._store_word_from_state(conn, word_info)

            conn.commit()
            self._set_last_processed_event_id(layout, last_event_id)

            return len(events)

    def _get_language_from_layout(self, layout: str) -> Optional[str]:
        """Get language code from layout identifier.

        Also checks loaded dictionaries to ensure language is available.
        If mapped language is not loaded, returns None to allow
        validation against all loaded dictionaries.

        Args:
            layout: Keyboard layout (e.g., 'us', 'de', 'gb')

        Returns:
            Language code ('en', 'de') or None
        """
        layout_map = {
            # English layouts
            "us": "en",
            "usa": "en",
            "gb": "en",
            "uk": "en",
            "ca": "en",
            "au": "en",
            "nz": "en",
            # German layouts
            "de": "de",
            "at": "de",
            "ch": "de",
            # French layouts
            "fr": "fr",
            "be": "fr",
            # Spanish layouts
            "es": "es",
            "latam": "es",
            # Italian layouts
            "it": "it",
            # Portuguese layouts
            "pt": "pt",
            "br": "pt",
            # Dutch layouts
            "nl": "nl",
            # Polish layouts
            "pl": "pl",
            # Russian layouts
            "ru": "ru",
        }

        layout_lower = layout.lower()
        language = layout_map.get(layout_lower)

        # Get loaded languages
        loaded_languages = self.dictionary.get_loaded_languages()

        # If no dictionaries are loaded, return None to validate against all
        if language and not loaded_languages:
            return None

        # If the mapped language is not loaded, return None to validate against all
        if language and language not in loaded_languages:
            return None

        # If multiple dictionaries are loaded, check all of them
        # This allows users to type in multiple languages regardless of keyboard layout
        if loaded_languages and len(loaded_languages) > 1:
            return None

        return language

    def _store_word_from_state(
        self, conn: sqlite3.Connection, word_info: WordInfo
    ) -> None:
        """Store word from WordDetector state with editing metadata.

        Args:
            conn: Database connection
            word_info: Word info from WordDetector
        """
        word = word_info.word
        layout = word_info.layout
        total_duration_ms = word_info.total_duration_ms
        editing_time_ms = word_info.editing_time_ms
        backspace_count = word_info.backspace_count
        num_letters = word_info.num_letters

        speed_per_letter = total_duration_ms / num_letters
        now_ms = int(time.time() * 1000)

        conn.execute(
            """
            INSERT INTO word_statistics
            (word, layout, avg_speed_ms_per_letter, total_letters,
             total_duration_ms, observation_count, last_seen,
             backspace_count, editing_time_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(word, layout) DO UPDATE SET
                avg_speed_ms_per_letter =
                    (avg_speed_ms_per_letter * observation_count + ?) / (observation_count + 1),
                total_letters = total_letters + ?,
                total_duration_ms = total_duration_ms + ?,
                observation_count = observation_count + 1,
                last_seen = ?,
                backspace_count = backspace_count + ?,
                editing_time_ms = editing_time_ms + ?
        """,
            (
                word,
                layout,
                speed_per_letter,
                num_letters,
                total_duration_ms,
                1,
                now_ms,
                backspace_count,
                editing_time_ms,
                speed_per_letter,
                num_letters,
                total_duration_ms,
                now_ms,
                backspace_count,
                editing_time_ms,
            ),
        )

    def get_slowest_words(
        self, limit: int = 10, layout: Optional[str] = None
    ) -> List[WordStatisticsLite]:
        """Get slowest words (highest average time per letter).

        Args:
            limit: Maximum number of words to return
            layout: Filter by layout (None for all layouts)

        Returns:
            List of WordStatisticsLite models
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if layout:
                cursor.execute(
                    """
                    SELECT word, avg_speed_ms_per_letter,
                           total_duration_ms, total_letters
                    FROM word_statistics
                    WHERE layout = ? AND observation_count >= 2
                    ORDER BY avg_speed_ms_per_letter DESC
                    LIMIT ?
                """,
                    (layout, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT word, avg_speed_ms_per_letter,
                           total_duration_ms, total_letters
                    FROM word_statistics
                    WHERE observation_count >= 2
                    ORDER BY avg_speed_ms_per_letter DESC
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
                )
                for r in rows
            ]

    def get_fastest_words(
        self, limit: int = 10, layout: Optional[str] = None
    ) -> List[WordStatisticsLite]:
        """Get fastest words (lowest average time per letter).

        Args:
            limit: Maximum number of words to return
            layout: Filter by layout (None for all layouts)

        Returns:
            List of WordStatisticsLite models
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if layout:
                cursor.execute(
                    """
                    SELECT word, avg_speed_ms_per_letter,
                           total_duration_ms, total_letters
                    FROM word_statistics
                    WHERE layout = ? AND observation_count >= 2
                    ORDER BY avg_speed_ms_per_letter ASC
                    LIMIT ?
                """,
                    (layout, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT word, avg_speed_ms_per_letter,
                           total_duration_ms, total_letters
                    FROM word_statistics
                    WHERE observation_count >= 2
                    ORDER BY avg_speed_ms_per_letter ASC
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
                )
                for r in rows
            ]

    def get_bursts_for_timeseries(
        self, start_ms: int, end_ms: int
    ) -> List[BurstTimeSeries]:
        """Get burst data for time-series graph.

        Args:
            start_ms: Start timestamp (milliseconds since epoch)
            end_ms: End timestamp (milliseconds since epoch)

        Returns:
            List of BurstTimeSeries models
        """
        with self._get_connection() as conn:
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

    def get_typing_time_by_granularity(
        self,
        granularity: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 90,
    ) -> List[TypingTimeDataPoint]:
        """Get typing time aggregated by time granularity.

        Args:
            granularity: Time period granularity ("day", "week", "month", "quarter")
            start_date: Optional start date (defaults to limit periods ago)
            end_date: Optional end date (defaults to now)
            limit: Maximum number of periods to return

        Returns:
            List of TypingTimeDataPoint models ordered by period_start
        """
        # Calculate date range
        if end_date:
            end_ms = int(
                (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)).timestamp()
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
            # Extract start of day in milliseconds
            group_by = "strftime('%Y-%m-%d', (start_time / 1000), 'unixepoch')"
        elif granularity == "week":
            # Extract start of week (Monday) in milliseconds
            group_by = "strftime('%Y-%W', (start_time / 1000), 'unixepoch')"
        elif granularity == "month":
            # Extract start of month
            group_by = "strftime('%Y-%m', (start_time / 1000), 'unixepoch')"
        elif granularity == "quarter":
            # Extract year and quarter
            group_by = "strftime('%Y-', (start_time / 1000), 'unixepoch') || ((CAST(strftime('%m', (start_time / 1000), 'unixepoch') AS INTEGER) - 1) / 3 + 1)"
        else:
            log.warning(f"Unknown granularity: {granularity}, defaulting to day")
            group_by = "strftime('%Y-%m-%d', (start_time / 1000), 'unixepoch')"

        with self._get_connection() as conn:
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
                    period_label = period_key  # Already in YYYY-MM-DD format
                elif granularity == "week":
                    # period_key is YYYY-WW format
                    year, week = period_key.split("-")
                    period_label = f"{year}-W{week}"
                elif granularity == "month":
                    period_label = period_key  # Already in YYYY-MM format
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
        """Calculate the end timestamp for a period.

        Args:
            period_start_ms: Period start timestamp in milliseconds
            granularity: Time period granularity

        Returns:
            Period end timestamp in milliseconds
        """
        start_dt = datetime.fromtimestamp(period_start_ms / 1000)

        if granularity == "day":
            end_dt = start_dt + timedelta(days=1)
        elif granularity == "week":
            end_dt = start_dt + timedelta(weeks=1)
        elif granularity == "month":
            # Add 1 month
            if start_dt.month == 12:
                end_dt = start_dt.replace(year=start_dt.year + 1, month=1)
            else:
                end_dt = start_dt.replace(month=start_dt.month + 1)
        elif granularity == "quarter":
            # Add 3 months
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

    def _format_period_label(self, period_start_ms: int, granularity: str) -> str:
        """Format period timestamp into human-readable label.

        Args:
            period_start_ms: Period start timestamp in milliseconds
            granularity: Time period granularity

        Returns:
            Formatted period label
        """
        dt = datetime.fromtimestamp(period_start_ms / 1000)

        if granularity == "day":
            return dt.strftime("%Y-%m-%d")
        elif granularity == "week":
            # ISO week number
            iso_week = dt.isocalendar()[1]
            return f"{dt.year}-W{iso_week:02d}"
        elif granularity == "month":
            return dt.strftime("%Y-%m")
        elif granularity == "quarter":
            quarter = (dt.month - 1) // 3 + 1
            return f"{dt.year}-Q{quarter}"
        else:
            return dt.strftime("%Y-%m-%d")
