"""Analyzer for typing statistics and high scores."""

import logging
import threading
import time
from datetime import datetime
from typing import Any

from core.burst_detector import Burst
from core.models import (
    BurstTimeSeries,
    DailySummaryDB,
    DigraphPerformance,
    KeyPerformance,
    TypingTimeDataPoint,
    WordStatisticsLite,
    WorstLetterChange,
)
from core.storage import Storage
from utils.keycodes import is_letter_key

log = logging.getLogger("realtypecoach.analyzer")

# Maximum gap between keystrokes to consider them part of continuous typing
# Same as burst_timeout_ms in BurstDetectorConfig
BURST_TIMEOUT_MS = 1000


class Analyzer:
    """Analyzes typing data and computes statistics.

    The analyzer delegates database queries to the Storage layer, which in turn
    delegates to the DatabaseAdapter. For simple read operations, the analyzer
    uses storage.db to access the database adapter directly, reducing indirection.
    """

    def __init__(self, storage: Storage):
        """Initialize analyzer.

        Args:
            storage: Storage instance for database operations
        """
        self.storage = storage
        self.running = False
        self.thread: threading.Thread | None = None

        self.today_date = datetime.now().strftime("%Y-%m-%d")
        self.today_stats: dict[str, Any] = {
            "total_keystrokes": 0,
            "total_bursts": 0,
            "total_typing_ms": 0,
            "slowest_keycode": None,
            "slowest_key_name": None,
            "total_backspaces": 0,
        }

        self.current_wpm: float = 0.0
        self.current_burst_wpm: float = 0.0
        self.personal_best_today: float | None = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

        # Worst letter tracking state
        self.worst_letter_keycode: int | None = None
        self.worst_letter_key_name: str | None = None
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
        summary = self.storage.db.get_daily_summary(self.today_date)
        if summary:
            self.today_stats["total_keystrokes"] = summary.total_keystrokes
            self.today_stats["total_bursts"] = summary.total_bursts
            # Don't load total_typing_ms - calculate fresh from database to avoid double-counting
            if summary.slowest_keycode and summary.slowest_key_name:
                self.today_stats["slowest_keycode"] = summary.slowest_keycode
                self.today_stats["slowest_key_name"] = summary.slowest_key_name
        else:
            # No daily summary yet, calculate from bursts
            startOfDay = int(datetime.strptime(self.today_date, "%Y-%m-%d").timestamp() * 1000)
            endOfDay = startOfDay + 86400000

            # Get burst statistics using adapter
            total_keystrokes, total_bursts = self.storage.db.get_burst_stats_for_date_range(
                startOfDay, endOfDay
            )
            self.today_stats["total_keystrokes"] = total_keystrokes
            self.today_stats["total_bursts"] = total_bursts

            # Don't load total_typing_ms from database to avoid double-counting
            # It will be accumulated as bursts are processed, and calculated fresh from DB in get_statistics
            self.today_stats["total_typing_ms"] = 0

        # Load personal best for today
        self.personal_best_today = self.storage.db.get_today_high_score(self.today_date)

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

        # Process keystroke through WordDetector immediately (no database storage)
        is_letter = is_letter_key(key_name)
        word_info = self.storage.word_detector.process_keystroke(
            key_name, timestamp_ms, layout, is_letter, keycode
        )

        # If a word was completed, update statistics from it
        if word_info and self.storage.dictionary.is_valid_word(
            word_info.word, self.storage._get_language_from_layout(layout)
        ):
            with self.storage._get_connection() as conn:
                self.storage._store_word_from_state(conn, word_info)
                conn.commit()

        with self._lock:
            self.today_stats["total_keystrokes"] += 1

    def process_burst(self, burst: Burst, max_wpm_threshold: int = 300) -> None:
        """Process a completed burst.

        Args:
            burst: Completed Burst object
            max_wpm_threshold: Maximum WPM to consider realistic (default: 300)
        """
        if burst.key_count == 0:
            return

        burst_wpm = self._calculate_wpm(burst.key_count, burst.duration_ms, burst.backspace_count)

        # Validate WPM is within realistic range
        if burst_wpm > max_wpm_threshold:
            log.warning(
                f"Ignored unrealistic burst: {burst_wpm:.1f} WPM > {max_wpm_threshold} WPM threshold, "
                f"{burst.key_count} keys, {burst.duration_ms / 1000:.1f}s"
            )
            return  # Early return - no storage, no stats update

        with self._lock:
            self.today_stats["total_bursts"] += 1
            self.today_stats["total_typing_ms"] += burst.duration_ms
            self.today_stats["total_backspaces"] += burst.backspace_count

        self.current_burst_wpm = burst_wpm

        self.storage.store_burst(burst, burst_wpm)

        if burst.qualifies_for_high_score:
            self._check_high_score(burst_wpm, burst.duration_ms, burst.key_count)

    def _calculate_wpm(self, key_count: int, duration_ms: int, backspace_count: int = 0) -> float:
        """Calculate words per minute.

        Uses NET productive keystrokes (total - 2*backspaces).
        Each backspace subtracts 2: 1 for the deleted character, 1 for the backspace itself.

        Standard: 5 characters = 1 word

        Args:
            key_count: Number of keystrokes (gross)
            duration_ms: Duration in milliseconds
            backspace_count: Number of backspace keystrokes

        Returns:
            WPM (words per minute)
        """
        from core.wpm_calculator import calculate_wpm, calculate_net_keystrokes
        net_keystrokes = calculate_net_keystrokes(key_count, backspace_count)
        return calculate_wpm(net_keystrokes, duration_ms)

    def _check_high_score(self, wpm: float, duration_ms: int, key_count: int) -> None:
        """Check if burst is a high score.

        Args:
            wpm: Words per minute
            duration_ms: Burst duration in milliseconds
            key_count: Number of keystrokes
        """
        today_high = self.storage.db.get_today_high_score(self.today_date)

        if today_high is None or wpm > today_high:
            self.storage.store_high_score(self.today_date, wpm, duration_ms, key_count)
            self.personal_best_today = wpm

    def _new_day(self, new_date: str) -> None:
        """Start a new day and finalize previous day.

        Args:
            new_date: New date string (YYYY-MM-DD)
        """
        # Hold lock during entire transition to prevent race condition
        with self._lock:
            old_date = self.today_date
            old_stats = {
                "total_keystrokes": self.today_stats["total_keystrokes"],
                "total_bursts": self.today_stats["total_bursts"],
                "slowest_keycode": self.today_stats["slowest_keycode"],
                "slowest_key_name": self.today_stats["slowest_key_name"],
                "total_backspaces": self.today_stats["total_backspaces"],
            }

            # Reset state for new day
            self.today_date = new_date
            self.personal_best_today = None

            self.today_stats = {
                "total_keystrokes": 0,
                "total_bursts": 0,
                "total_typing_ms": 0,
                "slowest_keycode": None,
                "slowest_key_name": None,
                "total_backspaces": 0,
            }

        # Finalize previous day outside lock (database operation - slow)
        # Note: Any events that arrive during this window will be counted toward the new day
        if old_stats["total_keystrokes"] > 0:
            self._finalize_day(old_date, old_stats)

    def _finalize_day(self, date: str, stats: dict) -> None:
        """Finalize current day's statistics.

        Args:
            date: Date string to finalize
            stats: Statistics for the day
        """
        # Calculate total typing time from database
        startOfDay = int(datetime.strptime(date, "%Y-%m-%d").timestamp() * 1000)
        endOfDay = startOfDay + 86400000

        total_typing_ms = self.storage.db.get_total_burst_duration(startOfDay, endOfDay)

        # Use backspace count for accurate WPM calculation
        avg_wpm = self._calculate_wpm(
            stats["total_keystrokes"], total_typing_ms, stats.get("total_backspaces", 0)
        )

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
        # Acquire lock before reading stats for thread safety
        with self._lock:
            if self.today_stats["total_keystrokes"] == 0:
                self.current_wpm = 0.0
                return

            total_keystrokes = self.today_stats["total_keystrokes"]
            total_backspaces = self.today_stats["total_backspaces"]
            today_date = self.today_date

        # Calculate total typing time from database
        startOfDay = int(datetime.strptime(today_date, "%Y-%m-%d").timestamp() * 1000)
        endOfDay = startOfDay + 86400000

        total_typing_ms = self.storage.db.get_total_burst_duration(startOfDay, endOfDay)

        total_time_sec = total_typing_ms / 1000.0
        if total_time_sec == 0:
            self.current_wpm = 0.0
            return

        self.current_wpm = self._calculate_wpm(total_keystrokes, total_typing_ms, total_backspaces)

    def get_statistics(self) -> dict:
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
            personal_best = self.personal_best_today
            current_wpm = self.current_wpm
            current_burst_wpm = self.current_burst_wpm

        # Calculate total typing time from database to avoid double-counting
        total_typing_ms = self.storage.db.get_today_typing_time(today_date)
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
        }

    def get_slowest_keys(self, limit: int = 10, layout: str | None = None) -> list[KeyPerformance]:
        """Get slowest keys from database.

        Args:
            limit: Maximum number to return
            layout: Filter by layout

        Returns:
            List of KeyPerformance models
        """
        return self.storage.db.get_slowest_keys(limit, layout)

    def get_fastest_keys(self, limit: int = 10, layout: str | None = None) -> list[KeyPerformance]:
        """Get fastest keys from database.

        Args:
            limit: Maximum number to return
            layout: Filter by layout

        Returns:
            List of KeyPerformance models
        """
        return self.storage.db.get_fastest_keys(limit, layout)

    def get_slowest_words(
        self, limit: int = 10, layout: str | None = None
    ) -> list[WordStatisticsLite]:
        """Get slowest words from database.

        Args:
            limit: Maximum number to return
            layout: Filter by layout

        Returns:
            List of WordStatisticsLite models
        """
        return self.storage.db.get_slowest_words(limit, layout)

    def get_fastest_words(
        self, limit: int = 10, layout: str | None = None
    ) -> list[WordStatisticsLite]:
        """Get fastest words from database.

        Args:
            limit: Maximum number to return
            layout: Filter by layout

        Returns:
            List of WordStatisticsLite models
        """
        return self.storage.db.get_fastest_words(limit, layout)

    def get_slowest_digraphs(
        self, limit: int = 10, layout: str | None = None
    ) -> list[DigraphPerformance]:
        """Get slowest digraphs from database.

        Args:
            limit: Maximum number to return
            layout: Filter by layout

        Returns:
            List of DigraphPerformance models
        """
        return self.storage.db.get_slowest_digraphs(limit, layout)

    def get_fastest_digraphs(
        self, limit: int = 10, layout: str | None = None
    ) -> list[DigraphPerformance]:
        """Get fastest digraphs from database.

        Args:
            limit: Maximum number to return
            layout: Filter by layout

        Returns:
            List of DigraphPerformance models
        """
        return self.storage.db.get_fastest_digraphs(limit, layout)

    def get_long_term_average_wpm(self) -> float | None:
        """Get long-term average WPM across all recorded bursts.

        Returns:
            Average WPM or None if no bursts recorded
        """
        return self.storage.db.get_average_burst_wpm()

    def get_all_time_high_score(self) -> float | None:
        """Get all-time highest WPM.

        Returns:
            WPM or None if no bursts recorded
        """
        return self.storage.db.get_all_time_high_score()

    def get_burst_wpm_percentile(self, percentile: float) -> float | None:
        """Get WPM value at a given percentile across all bursts.

        Args:
            percentile: Percentile value (0-100), e.g., 95 for 95th percentile

        Returns:
            WPM value at the percentile or None if no bursts recorded
        """
        return self.storage.db.get_burst_wpm_percentile(percentile)

    def is_exceptional_burst(self, wpm: float, percentile: float = 95) -> bool:
        """Check if a burst WPM is exceptional (exceeds the given percentile).

        Args:
            wpm: The WPM value to check
            percentile: Percentile threshold (default: 95)

        Returns:
            True if WPM exceeds the percentile threshold, False otherwise
        """
        threshold = self.get_burst_wpm_percentile(percentile)
        return threshold is not None and wpm > threshold

    def _check_worst_letter_change(self) -> WorstLetterChange | None:
        """Check if worst letter has changed and return change data.

        Returns:
            WorstLetterChange if changed and debounce elapsed, None otherwise
        """
        with self._lock:
            # Get current worst letter from database
            slowest_keys = self.storage.db.get_slowest_keys(limit=1, layout=None)

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
                    improvement=current_worst.avg_press_time < self.worst_letter_avg_time,
                )

                # Update state
                self.worst_letter_keycode = current_worst.keycode
                self.worst_letter_key_name = current_worst.key_name
                self.worst_letter_avg_time = current_worst.avg_press_time
                self.last_worst_letter_notification = current_time_ms

                return change

        return None

    def get_daily_summary(self, date: str) -> DailySummaryDB | None:
        """Get daily summary for a date.

        Args:
            date: Date string (YYYY-MM-DD)

        Returns:
            DailySummaryDB model or None
        """
        return self.storage.db.get_daily_summary(date)

    def get_wpm_time_series(self) -> list[BurstTimeSeries]:
        """Get WPM time series with timestamps for trend calculation.

        Returns:
            List of BurstTimeSeries models ordered by start_time
        """
        return self.storage.db.get_all_bursts_with_timestamps()

    def get_wpm_burst_sequence(self, smoothness: int = 1) -> tuple[list[float], list[int]]:
        """Get WPM values over burst sequence with exponential smoothing.

        Args:
            smoothness: Smoothing level (1-100) - NOTE: Parameter kept for API compatibility
                        but smoothing is now done client-side for instant response.

        Returns:
            Tuple of (raw_wpm_values, x_positions) where x_positions are burst numbers
        """
        # Get all bursts ordered by time from Storage facade
        raw_wpm = self.storage.db.get_all_burst_wpms_ordered()

        if not raw_wpm:
            return [], []

        # Return raw data - UI handles smoothing for instant slider response
        return raw_wpm, list(range(1, len(raw_wpm) + 1))

    def get_typing_time_data(
        self,
        granularity: str = "day",
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 90,
    ) -> list[TypingTimeDataPoint]:
        """Get typing time aggregated by time granularity.

        Args:
            granularity: Time period granularity ("day", "week", "month", "quarter")
            start_date: Optional start date (YYYY-MM-DD)
            end_date: Optional end date (YYYY-MM-DD)
            limit: Maximum number of periods to return

        Returns:
            List of TypingTimeDataPoint models
        """
        return self.storage.db.get_typing_time_by_granularity(
            granularity=granularity,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )

    def get_burst_wpm_histogram(self, bin_count: int = 50) -> list[tuple[float, int]]:
        """Get burst WPM distribution as histogram data.

        Args:
            bin_count: Number of histogram bins (10-200)

        Returns:
            List of (bin_center_wpm, count) tuples
        """
        return self.storage.db.get_burst_wpm_histogram(bin_count=bin_count)
