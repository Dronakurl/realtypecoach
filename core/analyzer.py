"""Analyzer for typing statistics and high scores."""

import logging
import sqlite3
from typing import Optional, Dict, List, Any
from collections import defaultdict
from datetime import datetime
import threading

from core.storage import Storage
from core.burst_detector import Burst
from core.models import DailySummaryDB, KeyPerformance, WordStatisticsLite

log = logging.getLogger('realtypecoach.analyzer')


class Analyzer:
    """Analyzes typing data and computes statistics."""

    def __init__(self, storage: Storage):
        """Initialize analyzer.

        Args:
            storage: Storage instance for database operations
        """
        self.storage = storage
        self.running = False
        self.thread: Optional[threading.Thread] = None

        self.today_date = datetime.now().strftime('%Y-%m-%d')
        self.today_stats: Dict[str, Any] = {
            'total_keystrokes': 0,
            'total_bursts': 0,
            'total_typing_ms': 0,
            'slowest_keycode': None,
            'slowest_key_name': None,
            'slowest_ms': 0.0,
            'keypress_times': defaultdict(list),  # List of intervals for each key
            'last_press_time': {},  # Last press timestamp for each key
        }

        self.current_wpm: float = 0.0
        self.current_burst_wpm: float = 0.0
        self.personal_best_today: Optional[float] = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

        # Load today's existing data from database
        self._load_today_data()

    def start(self) -> None:
        """Start analyzer background thread."""
        if self.running:
            return

        self.running = True
        self._stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        """Stop analyzer."""
        self.running = False
        self._stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)

    def _load_today_data(self) -> None:
        """Load today's existing data from database."""
        # Load daily summary if exists
        summary = self.storage.get_daily_summary(self.today_date)
        if summary:
            self.today_stats['total_keystrokes'] = summary.total_keystrokes
            self.today_stats['total_bursts'] = summary.total_bursts
            # Don't load total_typing_ms - calculate fresh from database to avoid double-counting
            if summary.slowest_keycode and summary.slowest_key_name:
                self.today_stats['slowest_keycode'] = summary.slowest_keycode
                self.today_stats['slowest_key_name'] = summary.slowest_key_name
        else:
            # No daily summary yet, calculate from raw data
            with sqlite3.connect(self.storage.db_path) as conn:
                cursor = conn.cursor()

                # Count today's keystrokes
                startOfDay = int(datetime.strptime(self.today_date, '%Y-%m-%d').timestamp() * 1000)
                endOfDay = startOfDay + 86400000

                cursor.execute('''
                    SELECT COUNT(*) FROM key_events
                    WHERE timestamp_ms >= ? AND timestamp_ms < ?
                ''', (startOfDay, endOfDay))
                self.today_stats['total_keystrokes'] = cursor.fetchone()[0]

                # Count today's bursts
                cursor.execute('''
                    SELECT COUNT(*) FROM bursts
                    WHERE start_time >= ? AND start_time < ?
                ''', (startOfDay, endOfDay))
                self.today_stats['total_bursts'] = cursor.fetchone()[0]

                # Don't load total_typing_ms from database to avoid double-counting
                # It will be accumulated as bursts are processed, and calculated fresh from DB in get_statistics
                self.today_stats['total_typing_ms'] = 0

        # Load personal best for today
        self.personal_best_today = self.storage.get_today_high_score(self.today_date)

    def process_key_event(self, keycode: int, key_name: str,
                          timestamp_ms: int,
                          layout: str = 'us') -> None:
        """Process a single key event.

        Args:
            keycode: Linux evdev keycode
            key_name: Human-readable key name
            timestamp_ms: Timestamp in milliseconds since epoch
            layout: Keyboard layout
        """
        now = datetime.now()
        current_date = now.strftime('%Y-%m-%d')

        with self._lock:
            if current_date != self.today_date:
                needs_new_day = True
            else:
                needs_new_day = False

        if needs_new_day:
            self._new_day(current_date)

        # Store key event to database
        self.storage.store_key_event(keycode, key_name, timestamp_ms)

        press_time_ms = timestamp_ms

        with self._lock:
            self.today_stats['total_keystrokes'] += 1
            last_press = self.today_stats['last_press_time'].get(keycode)

        if last_press:
            time_between = press_time_ms - last_press
            with self._lock:
                self.today_stats['keypress_times'][keycode].append(time_between)

                if time_between > self.today_stats['slowest_ms']:
                    self.today_stats['slowest_ms'] = time_between
                    self.today_stats['slowest_keycode'] = keycode
                    self.today_stats['slowest_key_name'] = key_name

            self._update_key_statistics(keycode, key_name, time_between, layout)

        # Store current press time for next comparison
        with self._lock:
            self.today_stats['last_press_time'][keycode] = press_time_ms

    def process_burst(self, burst: Burst) -> None:
        """Process a completed burst.

        Args:
            burst: Completed Burst object
        """
        if burst.key_count == 0:
            return

        burst_wpm = self._calculate_wpm(burst.key_count, burst.duration_ms)

        with self._lock:
            self.today_stats['total_bursts'] += 1
            self.today_stats['total_typing_ms'] += burst.duration_ms

        self.current_burst_wpm = burst_wpm

        self.storage.store_burst(
            burst.start_time_ms,
            burst.end_time_ms,
            burst.key_count,
            burst.duration_ms,
            burst_wpm,
            burst.qualifies_for_high_score
        )

        if burst.qualifies_for_high_score:
            self._check_high_score(burst_wpm, burst.duration_ms, burst.key_count)

    def _calculate_wpm(self, key_count: int, duration_ms: int) -> float:
        """Calculate words per minute.

        Standard: 5 characters = 1 word

        Args:
            key_count: Number of keystrokes
            duration_ms: Duration in milliseconds

        Returns:
            WPM (words per minute)
        """
        if duration_ms == 0:
            return 0.0

        words = key_count / 5.0
        minutes = duration_ms / 60000.0
        return words / minutes if minutes > 0 else 0.0

    def _update_key_statistics(self, keycode: int, key_name: str,
                               press_time_ms: float, layout: str = 'us') -> None:
        """Update per-key statistics.

        Args:
            keycode: Linux evdev keycode
            key_name: Human-readable key name
            press_time_ms: Time since last press
            layout: Keyboard layout (default: 'us')
        """
        times = self.today_stats['keypress_times'].get(keycode, [])

        if not times:
            return

        avg_time = sum(times) / len(times)
        is_slowest = press_time_ms == max(times)
        is_fastest = press_time_ms == min(times)

        self.storage.update_key_statistics(
            keycode, key_name, layout, avg_time,
            is_slowest, is_fastest
        )

    def _check_high_score(self, wpm: float, duration_ms: int, key_count: int) -> None:
        """Check if burst is a high score.

        Args:
            wpm: Words per minute
            duration_ms: Burst duration in milliseconds
            key_count: Number of keystrokes
        """
        today_high = self.storage.get_today_high_score(self.today_date)

        if today_high is None or wpm > today_high:
            self.storage.store_high_score(
                self.today_date, wpm, duration_ms, key_count
            )
            self.personal_best_today = wpm

    def _new_day(self, new_date: str) -> None:
        """Start a new day and finalize previous day.

        Args:
            new_date: New date string (YYYY-MM-DD)
        """
        # Copy values under lock, then finalize outside lock
        with self._lock:
            old_date = self.today_date
            old_stats = {
                'total_keystrokes': self.today_stats['total_keystrokes'],
                'total_bursts': self.today_stats['total_bursts'],
                'slowest_keycode': self.today_stats['slowest_keycode'],
                'slowest_key_name': self.today_stats['slowest_key_name'],
            }

        # Finalize previous day (database operation - slow)
        if old_stats['total_keystrokes'] > 0:
            self._finalize_day(old_date, old_stats)

        # Reset state under lock
        with self._lock:
            self.today_date = new_date
            self.personal_best_today = None

            self.today_stats = {
                'total_keystrokes': 0,
                'total_bursts': 0,
                'total_typing_ms': 0,
                'slowest_keycode': None,
                'slowest_key_name': None,
                'slowest_ms': 0.0,
                'keypress_times': defaultdict(list),  # List of intervals for each key
                'last_press_time': {},  # Last press timestamp for each key
            }

    def _finalize_day(self, date: str, stats: dict) -> None:
        """Finalize current day's statistics.

        Args:
            date: Date string to finalize
            stats: Statistics dictionary for the day
        """
        # Calculate total typing time from database
        startOfDay = int(datetime.strptime(date, '%Y-%m-%d').timestamp() * 1000)
        endOfDay = startOfDay + 86400000

        with sqlite3.connect(self.storage.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COALESCE(SUM(duration_ms), 0) FROM bursts
                WHERE start_time >= ? AND start_time < ?
            ''', (startOfDay, endOfDay))
            total_typing_ms = cursor.fetchone()[0]

        avg_wpm = self._calculate_wpm(
            stats['total_keystrokes'],
            total_typing_ms
        )

        self.storage.update_daily_summary(
            date,
            stats['total_keystrokes'],
            stats['total_bursts'],
            avg_wpm,
            stats['slowest_keycode'] or 0,
            stats['slowest_key_name'] or 'unknown',
            total_typing_ms // 1000
        )

    def _run(self) -> None:
        """Background analyzer loop."""
        while not self._stop_event.is_set():
            self._stop_event.wait(60)  # Update every minute
            if not self._stop_event.is_set():
                self._update_current_wpm()

    def _update_current_wpm(self) -> None:
        """Update current WPM based on recent activity."""
        if self.today_stats['total_keystrokes'] == 0:
            self.current_wpm = 0.0
            return

        # Calculate total typing time from database
        startOfDay = int(datetime.strptime(self.today_date, '%Y-%m-%d').timestamp() * 1000)
        endOfDay = startOfDay + 86400000

        with sqlite3.connect(self.storage.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COALESCE(SUM(duration_ms), 0) FROM bursts
                WHERE start_time >= ? AND start_time < ?
            ''', (startOfDay, endOfDay))
            total_typing_ms = cursor.fetchone()[0]

        total_time_sec = total_typing_ms / 1000.0
        if total_time_sec == 0:
            self.current_wpm = 0.0
            return

        self.current_wpm = self._calculate_wpm(
            self.today_stats['total_keystrokes'],
            total_typing_ms
        )

    def get_statistics(self) -> Dict:
        """Get current statistics summary.

        Returns:
            Dictionary with statistics
        """
        # Copy values under lock
        with self._lock:
            today_date = self.today_date
            total_keystrokes = self.today_stats['total_keystrokes']
            total_bursts = self.today_stats['total_bursts']
            slowest_keycode = self.today_stats['slowest_keycode']
            slowest_key_name = self.today_stats['slowest_key_name']
            slowest_ms = self.today_stats['slowest_ms']
            personal_best = self.personal_best_today
            current_wpm = self.current_wpm
            current_burst_wpm = self.current_burst_wpm

        # Calculate total typing time from database to avoid double-counting
        startOfDay = int(datetime.strptime(today_date, '%Y-%m-%d').timestamp() * 1000)
        endOfDay = startOfDay + 86400000

        with sqlite3.connect(self.storage.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COALESCE(SUM(duration_ms), 0) FROM bursts
                WHERE start_time >= ? AND start_time < ?
            ''', (startOfDay, endOfDay))
            total_typing_ms = cursor.fetchone()[0]

        total_time_sec = total_typing_ms / 1000.0

        return {
            'date': today_date,
            'total_keystrokes': total_keystrokes,
            'total_bursts': total_bursts,
            'total_typing_sec': total_time_sec,
            'avg_wpm': current_wpm,
            'burst_wpm': current_burst_wpm,
            'personal_best_today': personal_best,
            'slowest_keycode': slowest_keycode,
            'slowest_key_name': slowest_key_name,
            'slowest_ms': slowest_ms,
        }

    def get_slowest_keys(self, limit: int = 10,
                          layout: Optional[str] = None) -> List[KeyPerformance]:
        """Get slowest keys from database.

        Args:
            limit: Maximum number to return
            layout: Filter by layout

        Returns:
            List of KeyPerformance models
        """
        return self.storage.get_slowest_keys(limit, layout)

    def get_fastest_keys(self, limit: int = 10,
                         layout: Optional[str] = None) -> List[KeyPerformance]:
        """Get fastest keys from database.

        Args:
            limit: Maximum number to return
            layout: Filter by layout

        Returns:
            List of KeyPerformance models
        """
        return self.storage.get_fastest_keys(limit, layout)

    def get_slowest_words(self, limit: int = 10,
                          layout: Optional[str] = None) -> List[WordStatisticsLite]:
        """Get slowest words from database.

        Args:
            limit: Maximum number to return
            layout: Filter by layout

        Returns:
            List of WordStatisticsLite models
        """
        current_layout = layout if layout else 'us'
        self.storage._process_new_key_events(layout=current_layout)
        return self.storage.get_slowest_words(limit, layout)

    def get_fastest_words(self, limit: int = 10,
                          layout: Optional[str] = None) -> List[WordStatisticsLite]:
        """Get fastest words from database.

        Args:
            limit: Maximum number to return
            layout: Filter by layout

        Returns:
            List of WordStatisticsLite models
        """
        current_layout = layout if layout else 'us'
        self.storage._process_new_key_events(layout=current_layout)
        return self.storage.get_fastest_words(limit, layout)

    def get_daily_summary(self, date: str) -> Optional[DailySummaryDB]:
        """Get daily summary for a date.

        Args:
            date: Date string (YYYY-MM-DD)

        Returns:
            DailySummaryDB model or None
        """
        return self.storage.get_daily_summary(date)

    def get_wpm_burst_sequence(self, window_size: int = 1) -> List[float]:
        """Get WPM values over burst sequence with sliding window aggregation.

        Args:
            window_size: Number of bursts to aggregate (1-50)
                        1 = no aggregation (each burst is one point)
                        50 = 50-burst sliding average

        Returns:
            List of WPM values (one per data point)
        """
        # Get all bursts ordered by time
        with sqlite3.connect(self.storage.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT avg_wpm FROM bursts ORDER BY start_time')
            raw_wpm = [row[0] for row in cursor.fetchall() if row[0] is not None]

        if not raw_wpm:
            return []

        # Apply sliding window if window_size > 1
        if window_size == 1:
            return raw_wpm
        else:
            # Calculate sliding window average
            import pandas as pd
            series = pd.Series(raw_wpm)
            rolling_avg = series.rolling(window=window_size, center=True, min_periods=1).mean()
            return rolling_avg.tolist()
