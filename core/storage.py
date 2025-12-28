"""Storage management for RealTypeCoach - SQLite database operations."""

import sqlite3
import time
from pathlib import Path
from typing import List, Optional, Tuple, Any
from datetime import datetime, timedelta


class Storage:
    """Database storage for typing data."""

    def __init__(self, db_path: Path):
        """Initialize storage with database at given path.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._init_database()

    def _init_database(self) -> None:
        """Create all database tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            self._create_key_events_table(conn)
            self._create_bursts_table(conn)
            self._create_statistics_table(conn)
            self._create_high_scores_table(conn)
            self._create_daily_summaries_table(conn)
            self._create_settings_table(conn)
            self._create_word_statistics_table(conn)
            conn.commit()

    def _create_key_events_table(self, conn: sqlite3.Connection) -> None:
        """Create key_events table."""
        conn.execute('''
            CREATE TABLE IF NOT EXISTS key_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keycode INTEGER NOT NULL,
                key_name TEXT NOT NULL,
                timestamp_ms INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                app_name TEXT,
                is_password_field INTEGER DEFAULT 0
            )
        ''')

    def _create_bursts_table(self, conn: sqlite3.Connection) -> None:
        """Create bursts table."""
        conn.execute('''
            CREATE TABLE IF NOT EXISTS bursts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_time INTEGER NOT NULL,
                end_time INTEGER NOT NULL,
                key_count INTEGER NOT NULL,
                duration_ms INTEGER NOT NULL,
                avg_wpm REAL,
                qualifies_for_high_score INTEGER DEFAULT 0
            )
        ''')

    def _create_statistics_table(self, conn: sqlite3.Connection) -> None:
        """Create statistics table."""
        conn.execute('''
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
        ''')

    def _create_high_scores_table(self, conn: sqlite3.Connection) -> None:
        """Create high_scores table."""
        conn.execute('''
            CREATE TABLE IF NOT EXISTS high_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                fastest_burst_wpm REAL,
                burst_duration_sec REAL,
                burst_key_count INTEGER,
                timestamp INTEGER NOT NULL
            )
        ''')

    def _create_daily_summaries_table(self, conn: sqlite3.Connection) -> None:
        """Create daily_summaries table."""
        conn.execute('''
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
        ''')

    def _create_settings_table(self, conn: sqlite3.Connection) -> None:
        """Create settings table."""
        conn.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        ''')

    def _create_word_statistics_table(self, conn: sqlite3.Connection) -> None:
        """Create word_statistics table."""
        conn.execute('''
            CREATE TABLE IF NOT EXISTS word_statistics (
                word TEXT NOT NULL,
                layout TEXT NOT NULL,
                avg_speed_ms_per_letter REAL NOT NULL,
                total_letters INTEGER NOT NULL,
                total_duration_ms INTEGER NOT NULL,
                observation_count INTEGER NOT NULL,
                last_seen INTEGER NOT NULL,
                PRIMARY KEY (word, layout)
            )
        ''')

    def store_key_event(self, keycode: int, key_name: str,
                     timestamp_ms: int, event_type: str,
                     app_name: str, is_password_field: bool) -> None:
        """Store a single key event.

        Args:
            keycode: Linux evdev keycode
            key_name: Human-readable key name
            timestamp_ms: Milliseconds since epoch
            event_type: 'press' or 'release'
            app_name: Application name
            is_password_field: Whether typing in password field
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO key_events
                (keycode, key_name, timestamp_ms, event_type, app_name, is_password_field)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (keycode, key_name, timestamp_ms, event_type,
                  app_name, int(is_password_field)))
            conn.commit()

    def store_burst(self, start_time: int, end_time: int,
                  key_count: int, duration_ms: int, avg_wpm: float,
                  qualifies_for_high_score: bool) -> None:
        """Store a burst.

        Args:
            start_time: Start timestamp (ms since epoch)
            end_time: End timestamp (ms since epoch)
            key_count: Number of keystrokes
            duration_ms: Burst duration in milliseconds
            avg_wpm: Average WPM during burst
            qualifies_for_high_score: Whether burst meets minimum duration
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO bursts
                (start_time, end_time, key_count, duration_ms, avg_wpm, qualifies_for_high_score)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (start_time, end_time, key_count, duration_ms, avg_wpm,
                  int(qualifies_for_high_score)))
            conn.commit()

    def update_key_statistics(self, keycode: int, key_name: str,
                            layout: str, press_time_ms: float,
                            is_slowest: bool, is_fastest: bool) -> None:
        """Update statistics for a key.

        Args:
            keycode: Linux evdev keycode
            key_name: Human-readable key name
            layout: Keyboard layout identifier
            press_time_ms: Time since last press
            is_slowest: Whether this is new slowest time
            is_fastest: Whether this is new fastest time
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT avg_press_time, total_presses, slowest_ms, fastest_ms
                FROM statistics WHERE keycode = ? AND layout = ?
            ''', (keycode, layout))

            result = cursor.fetchone()
            now_ms = int(time.time() * 1000)

            if result:
                avg_press, total_presses, slowest_ms, fastest_ms = result
                new_total = total_presses + 1

                new_avg = (avg_press * total_presses + press_time_ms) / new_total
                new_slowest = min(slowest_ms, press_time_ms) if slowest_ms else press_time_ms
                new_fastest = max(fastest_ms, press_time_ms) if fastest_ms else press_time_ms

                if is_slowest and slowest_ms:
                    new_slowest = press_time_ms
                if is_fastest and fastest_ms:
                    new_fastest = press_time_ms

                cursor.execute('''
                    UPDATE statistics SET
                        avg_press_time = ?, total_presses = ?, slowest_ms = ?,
                        fastest_ms = ?, last_updated = ?
                    WHERE keycode = ? AND layout = ?
                ''', (new_avg, new_total, new_slowest, new_fastest, now_ms,
                      keycode, layout))
            else:
                cursor.execute('''
                    INSERT INTO statistics
                    (keycode, key_name, layout, avg_press_time, total_presses,
                     slowest_ms, fastest_ms, last_updated)
                    VALUES (?, ?, ?, ?, 1, ?, ?, ?)
                ''', (keycode, key_name, layout, press_time_ms, press_time_ms,
                      press_time_ms, now_ms))

            conn.commit()

    def store_high_score(self, date: str, wpm: float,
                       duration_sec: float, key_count: int) -> None:
        """Store a high score for a date.

        Args:
            date: Date string (YYYY-MM-DD)
            wpm: Words per minute achieved
            duration_sec: Burst duration in seconds
            key_count: Number of keystrokes
        """
        timestamp_ms = int(time.time() * 1000)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO high_scores
                (date, fastest_burst_wpm, burst_duration_sec, burst_key_count, timestamp)
                VALUES (?, ?, ?, ?, ?)
            ''', (date, wpm, duration_sec, key_count, timestamp_ms))
            conn.commit()

    def get_today_high_score(self, date: str) -> Optional[float]:
        """Get today's highest WPM.

        Args:
            date: Date string (YYYY-MM-DD)

        Returns:
            WPM or None if no bursts today
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT MAX(fastest_burst_wpm) FROM high_scores WHERE date = ?
            ''', (date,))
            result = cursor.fetchone()
            return result[0] if result and result[0] else None

    def update_daily_summary(self, date: str, total_keystrokes: int,
                           total_bursts: int, avg_wpm: float,
                           slowest_keycode: int, slowest_key_name: str,
                           total_typing_sec: int) -> None:
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
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO daily_summaries
                (date, total_keystrokes, total_bursts, avg_wpm,
                 slowest_keycode, slowest_key_name, total_typing_sec)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (date, total_keystrokes, total_bursts, avg_wpm,
                  slowest_keycode, slowest_key_name, total_typing_sec))
            conn.commit()

    def get_slowest_keys(self, limit: int = 10,
                         layout: Optional[str] = None) -> List[Tuple[int, str, float]]:
        """Get slowest keys (highest average press time).

        Only includes letter keys (a-z, ä, ö, ü, ß).

        Args:
            limit: Maximum number of keys to return
            layout: Filter by layout (None for all layouts)

        Returns:
            List of (keycode, key_name, avg_press_time_ms) tuples
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if layout:
                cursor.execute('''
                    SELECT keycode, key_name, avg_press_time
                    FROM statistics
                    WHERE layout = ? AND total_presses >= 2
                        AND (key_name REGEXP '^[a-z]$' OR key_name IN ('ä', 'ö', 'ü', 'ß'))
                    ORDER BY avg_press_time DESC
                    LIMIT ?
                ''', (layout, limit))
            else:
                cursor.execute('''
                    SELECT keycode, key_name, avg_press_time
                    FROM statistics
                    WHERE total_presses >= 2
                        AND (key_name REGEXP '^[a-z]$' OR key_name IN ('ä', 'ö', 'ü', 'ß'))
                    ORDER BY avg_press_time DESC
                    LIMIT ?
                ''', (limit,))
            return cursor.fetchall()

    def get_fastest_keys(self, limit: int = 10,
                         layout: Optional[str] = None) -> List[Tuple[int, str, float]]:
        """Get fastest keys (lowest average press time).

        Only includes letter keys (a-z, ä, ö, ü, ß).

        Args:
            limit: Maximum number of keys to return
            layout: Filter by layout (None for all layouts)

        Returns:
            List of (keycode, key_name, avg_press_time_ms) tuples
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if layout:
                cursor.execute('''
                    SELECT keycode, key_name, avg_press_time
                    FROM statistics
                    WHERE layout = ? AND total_presses >= 2
                        AND (key_name REGEXP '^[a-z]$' OR key_name IN ('ä', 'ö', 'ü', 'ß'))
                    ORDER BY avg_press_time ASC
                    LIMIT ?
                ''', (layout, limit))
            else:
                cursor.execute('''
                    SELECT keycode, key_name, avg_press_time
                    FROM statistics
                    WHERE total_presses >= 2
                        AND (key_name REGEXP '^[a-z]$' OR key_name IN ('ä', 'ö', 'ü', 'ß'))
                    ORDER BY avg_press_time ASC
                    LIMIT ?
                ''', (limit,))
            return cursor.fetchall()

    def get_daily_summary(self, date: str) -> Optional[Tuple]:
        """Get daily summary for a date.

        Args:
            date: Date string (YYYY-MM-DD)

        Returns:
            Tuple with summary data or None if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT total_keystrokes, total_bursts, avg_wpm,
                       slowest_keycode, slowest_key_name, total_typing_sec, summary_sent
                FROM daily_summaries WHERE date = ?
            ''', (date,))
            return cursor.fetchone()

    def mark_summary_sent(self, date: str) -> None:
        """Mark daily summary as sent.

        Args:
            date: Date string (YYYY-MM-DD)
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                UPDATE daily_summaries SET summary_sent = 1 WHERE date = ?
            ''', (date,))
            conn.commit()

    def export_to_csv(self, csv_path: Path,
                     start_date: Optional[str] = None,
                     end_date: Optional[str] = None) -> int:
        """Export key events to CSV file.

        Args:
            csv_path: Path to save CSV file
            start_date: Start date string (YYYY-MM-DD) or None
            end_date: End date string (YYYY-MM-DD) or None

        Returns:
            Number of rows exported
        """
        query = '''
            SELECT timestamp_ms, keycode, key_name, event_type, app_name, is_password_field
            FROM key_events
        '''
        params = []

        if start_date:
            start_ms = int(datetime.strptime(start_date, '%Y-%m-%d').timestamp() * 1000)
            query += ' WHERE timestamp_ms >= ?'
            params.append(start_ms)

        if end_date:
            end_ms = int((datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)).timestamp() * 1000)
            if start_date:
                query += ' AND timestamp_ms < ?'
            else:
                query += ' WHERE timestamp_ms < ?'
            params.append(end_ms)

        query += ' ORDER BY timestamp_ms'

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()

            with open(csv_path, 'w') as f:
                f.write('timestamp_ms,keycode,key_name,event_type,app_name,is_password_field\n')
                for row in rows:
                    f.write(','.join(str(x) for x in row) + '\n')

            return len(rows)

    def delete_old_data(self, retention_days: int) -> None:
        """Delete data older than retention period.

        Args:
            retention_days: Number of days to keep
        """
        cutoff_ms = int((datetime.now() - timedelta(days=retention_days)).timestamp() * 1000)
        cutoff_date = (datetime.now() - timedelta(days=retention_days)).strftime('%Y-%m-%d')
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('DELETE FROM key_events WHERE timestamp_ms < ?', (cutoff_ms,))
            conn.execute('DELETE FROM bursts WHERE start_time < ?', (cutoff_ms,))
            conn.execute('DELETE FROM daily_summaries WHERE date < ?', (cutoff_date,))
            conn.commit()

    def clear_database(self) -> None:
        """Clear all data from database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('DELETE FROM key_events')
            conn.execute('DELETE FROM bursts')
            conn.execute('DELETE FROM statistics')
            conn.execute('DELETE FROM high_scores')
            conn.execute('DELETE FROM daily_summaries')
            conn.execute('DELETE FROM word_statistics')
            conn.execute('DELETE FROM settings WHERE key = ? OR key = ?', 
                        ('last_processed_event_id_us', 'last_processed_event_id_de'))
            conn.commit()

    def _is_letter_key(self, key_name: str) -> bool:
        """Check if key is a letter (a-z, A-Z, accented characters).

        Args:
            key_name: Key name from key events

        Returns:
            True if key is a letter, False otherwise
        """
        return len(key_name) == 1 and key_name.isalpha()

    def _is_word_boundary(self, key_name: str) -> bool:
        """Check if key marks a word boundary (not a letter).

        Args:
            key_name: Key name from key events

        Returns:
            True if key is a word boundary, False otherwise
        """
        return not self._is_letter_key(key_name)

    def update_word_statistics(self, word: str, layout: str, 
                               duration_ms: int, num_letters: int) -> None:
        """Update statistics for a word with running average.

        Args:
            word: The word that was typed
            layout: Keyboard layout identifier
            duration_ms: Time taken to type the word (ms)
            num_letters: Number of letters in the word
        """
        speed_per_letter = duration_ms / num_letters
        now_ms = int(time.time() * 1000)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT avg_speed_ms_per_letter, total_letters,
                       total_duration_ms, observation_count
                FROM word_statistics
                WHERE word = ? AND layout = ?
            ''', (word, layout))

            result = cursor.fetchone()

            if result:
                avg_speed, total_letters, total_duration, count = result
                new_count = count + 1
                new_avg_speed = (avg_speed * count + speed_per_letter) / new_count
                new_total_letters = total_letters + num_letters
                new_total_duration = total_duration + duration_ms

                cursor.execute('''
                    UPDATE word_statistics SET
                        avg_speed_ms_per_letter = ?,
                        total_letters = ?,
                        total_duration_ms = ?,
                        observation_count = ?,
                        last_seen = ?
                    WHERE word = ? AND layout = ?
                ''', (new_avg_speed, new_total_letters, new_total_duration,
                      new_count, now_ms, word, layout))
            else:
                cursor.execute('''
                    INSERT INTO word_statistics
                    (word, layout, avg_speed_ms_per_letter, total_letters,
                     total_duration_ms, observation_count, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (word, layout, speed_per_letter, num_letters,
                      duration_ms, 1, now_ms))

            conn.commit()

    def _get_last_processed_event_id(self, layout: str) -> int:
        """Get the last processed event ID for a layout.

        Args:
            layout: Keyboard layout identifier

        Returns:
            Last processed event ID, or 0 if none
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            setting_key = f'last_processed_event_id_{layout}'
            cursor.execute('''
                SELECT value FROM settings WHERE key = ?
            ''', (setting_key,))
            result = cursor.fetchone()
            return int(result[0]) if result else 0

    def _set_last_processed_event_id(self, layout: str, event_id: int) -> None:
        """Set the last processed event ID for a layout.

        Args:
            layout: Keyboard layout identifier
            event_id: Event ID to save
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            setting_key = f'last_processed_event_id_{layout}'
            cursor.execute('''
                INSERT OR REPLACE INTO settings (key, value)
                VALUES (?, ?)
            ''', (setting_key, str(event_id)))
            conn.commit()

    def _process_new_key_events(self, layout: str = 'us', 
                                max_events: int = 1000) -> int:
        """Process new key events to detect and update word statistics.

        Args:
            layout: Keyboard layout identifier
            max_events: Maximum number of events to process in one call

        Returns:
            Number of events processed
        """
        last_processed_id = self._get_last_processed_event_id(layout)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute('''
                SELECT id, key_name, timestamp_ms
                FROM key_events
                WHERE id > ? AND event_type = 'press' AND is_password_field = 0
                ORDER BY id
                LIMIT ?
            ''', (last_processed_id, max_events))

            events = cursor.fetchall()

            if not events:
                return 0

            current_word = []
            word_start_time = None
            last_event_id = last_processed_id

            for event_id, key_name, timestamp_ms in events:
                last_event_id = event_id

                if self._is_letter_key(key_name):
                    if not current_word:
                        word_start_time = timestamp_ms
                    current_word.append(key_name)
                elif self._is_word_boundary(key_name) and current_word:
                    word = ''.join(current_word)
                    num_letters = len(word)

                    if num_letters >= 3:
                        duration_ms = timestamp_ms - word_start_time
                        conn.execute('''
                            INSERT INTO word_statistics
                            (word, layout, avg_speed_ms_per_letter, total_letters,
                             total_duration_ms, observation_count, last_seen)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(word, layout) DO UPDATE SET
                                avg_speed_ms_per_letter = 
                                    (avg_speed_ms_per_letter * observation_count + ?) / (observation_count + 1),
                                total_letters = total_letters + ?,
                                total_duration_ms = total_duration_ms + ?,
                                observation_count = observation_count + 1,
                                last_seen = ?
                        ''', (word, layout, duration_ms / num_letters, num_letters,
                              duration_ms, 1, int(time.time() * 1000),
                              duration_ms / num_letters, num_letters, duration_ms,
                              int(time.time() * 1000)))

                    current_word = []
                    word_start_time = None

            conn.commit()
            self._set_last_processed_event_id(layout, last_event_id)

            return len(events)

    def get_slowest_words(self, limit: int = 10,
                         layout: Optional[str] = None) -> List[Tuple[str, float, int, int]]:
        """Get slowest words (highest average time per letter).

        Args:
            limit: Maximum number of words to return
            layout: Filter by layout (None for all layouts)

        Returns:
            List of (word, avg_speed_ms_per_letter, total_duration_ms, num_letters) tuples
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if layout:
                cursor.execute('''
                    SELECT word, avg_speed_ms_per_letter, 
                           total_duration_ms, total_letters
                    FROM word_statistics
                    WHERE layout = ? AND observation_count >= 2
                    ORDER BY avg_speed_ms_per_letter DESC
                    LIMIT ?
                ''', (layout, limit))
            else:
                cursor.execute('''
                    SELECT word, avg_speed_ms_per_letter,
                           total_duration_ms, total_letters
                    FROM word_statistics
                    WHERE observation_count >= 2
                    ORDER BY avg_speed_ms_per_letter DESC
                    LIMIT ?
                ''', (limit,))
            return cursor.fetchall()

    def get_fastest_words(self, limit: int = 10,
                          layout: Optional[str] = None) -> List[Tuple[str, float, int, int]]:
        """Get fastest words (lowest average time per letter).

        Args:
            limit: Maximum number of words to return
            layout: Filter by layout (None for all layouts)

        Returns:
            List of (word, avg_speed_ms_per_letter, total_duration_ms, num_letters) tuples
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if layout:
                cursor.execute('''
                    SELECT word, avg_speed_ms_per_letter,
                           total_duration_ms, total_letters
                    FROM word_statistics
                    WHERE layout = ? AND observation_count >= 2
                    ORDER BY avg_speed_ms_per_letter ASC
                    LIMIT ?
                ''', (layout, limit))
            else:
                cursor.execute('''
                    SELECT word, avg_speed_ms_per_letter,
                           total_duration_ms, total_letters
                    FROM word_statistics
                    WHERE observation_count >= 2
                    ORDER BY avg_speed_ms_per_letter ASC
                    LIMIT ?
                ''', (limit,))
            return cursor.fetchall()
