"""Analyzer for typing statistics and high scores."""

import time
from typing import Optional, Dict, Tuple
from collections import defaultdict
from datetime import datetime, timedelta
import threading

from core.storage import Storage
from core.burst_detector import Burst


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
        self.today_stats: Dict[str, any] = {
            'total_keystrokes': 0,
            'total_bursts': 0,
            'total_typing_ms': 0,
            'slowest_keycode': None,
            'slowest_key_name': None,
            'slowest_ms': 0.0,
            'keypress_times': defaultdict(list),
        }

        self.current_wpm: float = 0.0
        self.current_burst_wpm: float = 0.0
        self.personal_best_today: Optional[float] = None

    def start(self) -> None:
        """Start analyzer background thread."""
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        """Stop analyzer."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)

    def process_key_event(self, keycode: int, key_name: str,
                          timestamp_ms: int, event_type: str,
                          app_name: str, is_password_field: bool) -> None:
        """Process a single key event.

        Args:
            keycode: Linux evdev keycode
            key_name: Human-readable key name
            timestamp_ms: Timestamp in milliseconds since epoch
            event_type: 'press' or 'release'
            app_name: Application name
            is_password_field: Whether typing in password field
        """
        if is_password_field or event_type != 'press':
            return

        now = datetime.now()
        current_date = now.strftime('%Y-%m-%d')

        if current_date != self.today_date:
            self._new_day(current_date)

        self.today_stats['total_keystrokes'] += 1

        press_time_ms = timestamp_ms
        last_press = self.today_stats['keypress_times'].get(keycode)

        if last_press:
            time_between = press_time_ms - last_press
            self.today_stats['keypress_times'][keycode].append(time_between)

            if time_between > self.today_stats['slowest_ms']:
                self.today_stats['slowest_ms'] = time_between
                self.today_stats['slowest_keycode'] = keycode
                self.today_stats['slowest_key_name'] = key_name

            self._update_key_statistics(keycode, key_name, time_between)

    def process_burst(self, burst: Burst) -> None:
        """Process a completed burst.

        Args:
            burst: Completed Burst object
        """
        if burst.key_count == 0:
            return

        burst_wpm = self._calculate_wpm(burst.key_count, burst.duration_ms)
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
            self._check_high_score(burst_wpm, burst.duration_ms / 1000.0, burst.key_count)

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

    def _check_high_score(self, wpm: float, duration_sec: float, key_count: int) -> None:
        """Check if burst is a high score.

        Args:
            wpm: Words per minute
            duration_sec: Burst duration in seconds
            key_count: Number of keystrokes
        """
        today_high = self.storage.get_today_high_score(self.today_date)

        if today_high is None or wpm > today_high:
            self.storage.store_high_score(
                self.today_date, wpm, duration_sec, key_count
            )
            self.personal_best_today = wpm

    def _new_day(self, new_date: str) -> None:
        """Start a new day and finalize previous day.

        Args:
            new_date: New date string (YYYY-MM-DD)
        """
        self._finalize_day()
        self.today_date = new_date
        self.personal_best_today = None

        self.today_stats = {
            'total_keystrokes': 0,
            'total_bursts': 0,
            'total_typing_ms': 0,
            'slowest_keycode': None,
            'slowest_key_name': None,
            'slowest_ms': 0.0,
            'keypress_times': defaultdict(list),
        }

    def _finalize_day(self) -> None:
        """Finalize current day's statistics."""
        if self.today_stats['total_keystrokes'] == 0:
            return

        avg_wpm = self._calculate_wpm(
            self.today_stats['total_keystrokes'],
            self.today_stats['total_typing_ms']
        )

        self.storage.update_daily_summary(
            self.today_date,
            self.today_stats['total_keystrokes'],
            self.today_stats['total_bursts'],
            avg_wpm,
            self.today_stats['slowest_keycode'] or 0,
            self.today_stats['slowest_key_name'] or 'unknown',
            self.today_stats['total_typing_ms'] // 1000
        )

    def _run(self) -> None:
        """Background analyzer loop."""
        while self.running:
            time.sleep(60)  # Update every minute
            self._update_current_wpm()

    def _update_current_wpm(self) -> None:
        """Update current WPM based on recent activity."""
        if self.today_stats['total_keystrokes'] == 0:
            self.current_wpm = 0.0
            return

        total_time_sec = self.today_stats['total_typing_ms'] / 1000.0
        if total_time_sec == 0:
            self.current_wpm = 0.0
            return

        self.current_wpm = self._calculate_wpm(
            self.today_stats['total_keystrokes'],
            self.today_stats['total_typing_ms']
        )

    def get_statistics(self) -> Dict:
        """Get current statistics summary.

        Returns:
            Dictionary with statistics
        """
        total_time_sec = self.today_stats['total_typing_ms'] / 1000.0

        return {
            'date': self.today_date,
            'total_keystrokes': self.today_stats['total_keystrokes'],
            'total_bursts': self.today_stats['total_bursts'],
            'total_typing_sec': total_time_sec,
            'avg_wpm': self.current_wpm,
            'burst_wpm': self.current_burst_wpm,
            'personal_best_today': self.personal_best_today,
            'slowest_keycode': self.today_stats['slowest_keycode'],
            'slowest_key_name': self.today_stats['slowest_key_name'],
            'slowest_ms': self.today_stats['slowest_ms'],
        }

    def get_slowest_keys(self, limit: int = 10,
                          layout: Optional[str] = None) -> list:
        """Get slowest keys from database.

        Args:
            limit: Maximum number to return
            layout: Filter by layout

        Returns:
            List of (keycode, key_name, avg_time_ms) tuples
        """
        return self.storage.get_slowest_keys(limit, layout)

    def get_daily_summary(self, date: str) -> Optional[Tuple]:
        """Get daily summary for a date.

        Args:
            date: Date string (YYYY-MM-DD)

        Returns:
            Tuple with summary data or None
        """
        return self.storage.get_daily_summary(date)
