"""Analyzer for typing statistics and high scores."""

import logging
import time
from typing import Optional, Dict, List, Any
from collections import defaultdict
from datetime import datetime
import threading

from core.storage import Storage
from core.burst_detector import Burst
from core.models import (
    DailySummaryDB,
    KeyPerformance,
    WordStatisticsLite,
    DailyStats,
    WorstLetterChange,
    TypingTimeDataPoint,
)

log = logging.getLogger("realtypecoach.analyzer")

# Maximum gap between keystrokes to consider them part of continuous typing
# Same as burst_timeout_ms in BurstDetectorConfig
BURST_TIMEOUT_MS = 1000


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

        self.today_date = datetime.now().strftime("%Y-%m-%d")
        self.today_stats: dict[str, Any] = {
            "total_keystrokes": 0,
            "total_bursts": 0,
            "total_typing_ms": 0,
            "slowest_keycode": None,
            "slowest_key_name": None,
            "slowest_ms": 0.0,
            "keypress_times": defaultdict(list),
            "last_press_time": 0,
        }

        self.current_wpm: float = 0.0
        self.current_burst_wpm: float = 0.0
        self.personal_best_today: Optional[float] = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

        # Worst letter tracking state
        self.worst_letter_keycode: Optional[int] = None
        self.worst_letter_key_name: Optional[str] = None
        self.worst_letter_avg_time: float = 0.0
        self.last_worst_letter_notification: int = 0  # Timestamp of last notification
        self.worst_letter_debounce_ms: int = 300000  # 5 minutes default

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
            self.today_stats["total_keystrokes"] = summary.total_keystrokes
            self.today_stats["total_bursts"] = summary.total_bursts
            # Don't load total_typing_ms - calculate fresh from database to avoid double-counting
            if summary.slowest_keycode and summary.slowest_key_name:
                self.today_stats["slowest_keycode"] = summary.slowest_keycode
                self.today_stats["slowest_key_name"] = summary.slowest_key_name
        else:
            # No daily summary yet, calculate from raw data
            with self.storage._get_connection() as conn:
                cursor = conn.cursor()

                # Count today's keystrokes
                startOfDay = int(
                    datetime.strptime(self.today_date, "%Y-%m-%d").timestamp() * 1000
                )
                endOfDay = startOfDay + 86400000

                cursor.execute(
                    """
                    SELECT COUNT(*) FROM key_events
                    WHERE timestamp_ms >= ? AND timestamp_ms < ?
                """,
                    (startOfDay, endOfDay),
                )
                self.today_stats["total_keystrokes"] = cursor.fetchone()[0]

                # Count today's bursts
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM bursts
                    WHERE start_time >= ? AND start_time < ?
                """,
                    (startOfDay, endOfDay),
                )
                self.today_stats["total_bursts"] = cursor.fetchone()[0]

                # Don't load total_typing_ms from database to avoid double-counting
                # It will be accumulated as bursts are processed, and calculated fresh from DB in get_statistics
                self.today_stats["total_typing_ms"] = 0

        # Load personal best for today
        self.personal_best_today = self.storage.get_today_high_score(self.today_date)

    def process_key_event(
        self, keycode: int, key_name: str, timestamp_ms: int, layout: str = "us"
    ) -> None:
        """Process a single key event.

        Args:
            keycode: Linux evdev keycode
            key_name: Human-readable key name
            timestamp_ms: Timestamp in milliseconds since epoch
            layout: Keyboard layout
        """
        now = datetime.now()
        current_date = now.strftime("%Y-%m-%d")

        with self._lock:
            if current_date != self.today_date:
                needs_new_day = True
            else:
                needs_new_day = False

        if needs_new_day:
            self._new_day(current_date)

        # Store key event to database
        self.storage.store_key_event(keycode, key_name, timestamp_ms)

        with self._lock:
            self.today_stats["total_keystrokes"] += 1

        # Note: Key statistics are NO longer updated immediately here.
        # Instead, they are updated ONLY when processing valid dictionary words
        # in storage._process_keystroke_timings(). This ensures that letter speed
        # statistics only include keystrokes that are:
        # 1. Part of valid dictionary words
        # 2. Typed in bursts (within BURST_TIMEOUT_MS of each other)

    def process_burst(self, burst: Burst) -> None:
        """Process a completed burst.

        Args:
            burst: Completed Burst object
        """
        if burst.key_count == 0:
            return

        burst_wpm = self._calculate_wpm(burst.key_count, burst.duration_ms)

        with self._lock:
            self.today_stats["total_bursts"] += 1
            self.today_stats["total_typing_ms"] += burst.duration_ms

        self.current_burst_wpm = burst_wpm

        self.storage.store_burst(
            burst.start_time_ms,
            burst.end_time_ms,
            burst.key_count,
            burst.duration_ms,
            burst_wpm,
            burst.qualifies_for_high_score,
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

    def _check_high_score(self, wpm: float, duration_ms: int, key_count: int) -> None:
        """Check if burst is a high score.

        Args:
            wpm: Words per minute
            duration_ms: Burst duration in milliseconds
            key_count: Number of keystrokes
        """
        today_high = self.storage.get_today_high_score(self.today_date)

        if today_high is None or wpm > today_high:
            self.storage.store_high_score(self.today_date, wpm, duration_ms, key_count)
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
                "total_keystrokes": self.today_stats["total_keystrokes"],
                "total_bursts": self.today_stats["total_bursts"],
                "slowest_keycode": self.today_stats["slowest_keycode"],
                "slowest_key_name": self.today_stats["slowest_key_name"],
            }

        # Finalize previous day (database operation - slow)
        if old_stats["total_keystrokes"] > 0:
            self._finalize_day(old_date, old_stats)

        # Reset state under lock
        with self._lock:
            self.today_date = new_date
            self.personal_best_today = None

            self.today_stats = {
                "total_keystrokes": 0,
                "total_bursts": 0,
                "total_typing_ms": 0,
                "slowest_keycode": None,
                "slowest_key_name": None,
                "slowest_ms": 0.0,
                "keypress_times": defaultdict(list),
                "last_press_time": 0,
            }

    def _finalize_day(self, date: str, stats: DailyStats) -> None:
        """Finalize current day's statistics.

        Args:
            date: Date string to finalize
            stats: Statistics for the day
        """
        # Calculate total typing time from database
        startOfDay = int(datetime.strptime(date, "%Y-%m-%d").timestamp() * 1000)
        endOfDay = startOfDay + 86400000

        with self.storage._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COALESCE(SUM(duration_ms), 0) FROM bursts
                WHERE start_time >= ? AND start_time < ?
            """,
                (startOfDay, endOfDay),
            )
            total_typing_ms = cursor.fetchone()[0]

        avg_wpm = self._calculate_wpm(stats["total_keystrokes"], total_typing_ms)

        self.storage.update_daily_summary(
            date,
            stats["total_keystrokes"],
            stats["total_bursts"],
            avg_wpm,
            stats["slowest_keycode"] or 0,
            stats["slowest_key_name"] or "unknown",
            total_typing_ms // 1000,
        )

    def _run(self) -> None:
        """Background analyzer loop."""
        while not self._stop_event.is_set():
            self._stop_event.wait(60)  # Update every minute
            if not self._stop_event.is_set():
                self._update_current_wpm()

    def _update_current_wpm(self) -> None:
        """Update current WPM based on recent activity."""
        if self.today_stats["total_keystrokes"] == 0:
            self.current_wpm = 0.0
            return

        # Calculate total typing time from database
        startOfDay = int(
            datetime.strptime(self.today_date, "%Y-%m-%d").timestamp() * 1000
        )
        endOfDay = startOfDay + 86400000

        with self.storage._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COALESCE(SUM(duration_ms), 0) FROM bursts
                WHERE start_time >= ? AND start_time < ?
            """,
                (startOfDay, endOfDay),
            )
            total_typing_ms = cursor.fetchone()[0]

        total_time_sec = total_typing_ms / 1000.0
        if total_time_sec == 0:
            self.current_wpm = 0.0
            return

        self.current_wpm = self._calculate_wpm(
            self.today_stats["total_keystrokes"], total_typing_ms
        )

    def get_statistics(self) -> Dict:
        """Get current statistics summary.

        Returns:
            Dictionary with statistics
        """
        # Copy values under lock
        with self._lock:
            today_date = self.today_date
            total_keystrokes = self.today_stats["total_keystrokes"]
            total_bursts = self.today_stats["total_bursts"]
            slowest_keycode = self.today_stats["slowest_keycode"]
            slowest_key_name = self.today_stats["slowest_key_name"]
            slowest_ms = self.today_stats["slowest_ms"]
            personal_best = self.personal_best_today
            current_wpm = self.current_wpm
            current_burst_wpm = self.current_burst_wpm

        # Calculate total typing time from database to avoid double-counting
        startOfDay = int(datetime.strptime(today_date, "%Y-%m-%d").timestamp() * 1000)
        endOfDay = startOfDay + 86400000

        with self.storage._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COALESCE(SUM(duration_ms), 0) FROM bursts
                WHERE start_time >= ? AND start_time < ?
            """,
                (startOfDay, endOfDay),
            )
            total_typing_ms = cursor.fetchone()[0]

        total_time_sec = total_typing_ms / 1000.0

        return {
            "date": today_date,
            "total_keystrokes": total_keystrokes,
            "total_bursts": total_bursts,
            "total_typing_sec": total_time_sec,
            "avg_wpm": current_wpm,
            "burst_wpm": current_burst_wpm,
            "personal_best_today": personal_best,
            "slowest_keycode": slowest_keycode,
            "slowest_key_name": slowest_key_name,
            "slowest_ms": slowest_ms,
        }

    def get_slowest_keys(
        self, limit: int = 10, layout: Optional[str] = None
    ) -> List[KeyPerformance]:
        """Get slowest keys from database.

        Args:
            limit: Maximum number to return
            layout: Filter by layout

        Returns:
            List of KeyPerformance models
        """
        return self.storage.get_slowest_keys(limit, layout)

    def get_fastest_keys(
        self, limit: int = 10, layout: Optional[str] = None
    ) -> List[KeyPerformance]:
        """Get fastest keys from database.

        Args:
            limit: Maximum number to return
            layout: Filter by layout

        Returns:
            List of KeyPerformance models
        """
        return self.storage.get_fastest_keys(limit, layout)

    def get_slowest_words(
        self, limit: int = 10, layout: Optional[str] = None
    ) -> List[WordStatisticsLite]:
        """Get slowest words from database.

        Args:
            limit: Maximum number to return
            layout: Filter by layout

        Returns:
            List of WordStatisticsLite models
        """
        return self.storage.get_slowest_words(limit, layout)

    def get_fastest_words(
        self, limit: int = 10, layout: Optional[str] = None
    ) -> List[WordStatisticsLite]:
        """Get fastest words from database.

        Args:
            limit: Maximum number to return
            layout: Filter by layout

        Returns:
            List of WordStatisticsLite models
        """
        return self.storage.get_fastest_words(limit, layout)

    def get_long_term_average_wpm(self) -> Optional[float]:
        """Get long-term average WPM across all recorded bursts.

        Returns:
            Average WPM or None if no bursts recorded
        """
        with self.storage._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT AVG(avg_wpm) FROM bursts
                WHERE avg_wpm > 0
            """,
            )
            result = cursor.fetchone()
            return result[0] if result and result[0] else None

    def get_all_time_high_score(self) -> Optional[float]:
        """Get all-time highest WPM.

        Returns:
            WPM or None if no bursts recorded
        """
        return self.storage.get_all_time_high_score()

    def _check_worst_letter_change(self) -> Optional[WorstLetterChange]:
        """Check if worst letter has changed and return change data.

        Returns:
            WorstLetterChange if changed and debounce elapsed, None otherwise
        """
        with self._lock:
            # Get current worst letter from database
            slowest_keys = self.storage.get_slowest_keys(limit=1, layout=None)

            if not slowest_keys:
                return None

            current_worst = slowest_keys[0]
            current_time_ms = int(time.time() * 1000)

            # Check if debounce period has elapsed
            if (
                current_time_ms - self.last_worst_letter_notification
                < self.worst_letter_debounce_ms
            ):
                return None

            # Initialize on first run
            if self.worst_letter_keycode is None:
                self.worst_letter_keycode = current_worst.keycode
                self.worst_letter_key_name = current_worst.key_name
                self.worst_letter_avg_time = current_worst.avg_press_time
                return None

            # Check if worst letter changed
            if current_worst.keycode != self.worst_letter_keycode:
                # Prepare change data
                change = WorstLetterChange(
                    previous_key=self.worst_letter_key_name or "unknown",
                    new_key=current_worst.key_name,
                    previous_time_ms=self.worst_letter_avg_time,
                    new_time_ms=current_worst.avg_press_time,
                    timestamp=current_time_ms,
                    improvement=current_worst.avg_press_time
                    < self.worst_letter_avg_time,
                )

                # Update state
                self.worst_letter_keycode = current_worst.keycode
                self.worst_letter_key_name = current_worst.key_name
                self.worst_letter_avg_time = current_worst.avg_press_time
                self.last_worst_letter_notification = current_time_ms

                return change

        return None

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
            window_size: Number of bursts to aggregate (1-200)
                        1 = no aggregation (each burst is one point)
                        200 = 200-burst sliding average

        Returns:
            List of WPM values (one per data point)
        """
        # Get all bursts ordered by time
        with self.storage._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT avg_wpm FROM bursts ORDER BY start_time")
            raw_wpm = [row[0] for row in cursor.fetchall() if row[0] is not None]

        if not raw_wpm:
            return []

        # Apply sliding window if window_size > 1
        if window_size == 1:
            return raw_wpm
        else:
            # Calculate sliding window average (looking back at previous bursts)
            import pandas as pd

            series = pd.Series(raw_wpm)
            rolling_avg = series.rolling(
                window=window_size, center=False, min_periods=1
            ).mean()
            return rolling_avg.tolist()

    def get_typing_time_data(
        self,
        granularity: str = "day",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 90,
    ) -> List[TypingTimeDataPoint]:
        """Get typing time aggregated by time granularity.

        Args:
            granularity: Time period granularity ("day", "week", "month", "quarter")
            start_date: Optional start date (YYYY-MM-DD)
            end_date: Optional end date (YYYY-MM-DD)
            limit: Maximum number of periods to return

        Returns:
            List of TypingTimeDataPoint models
        """
        return self.storage.get_typing_time_by_granularity(
            granularity=granularity,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
