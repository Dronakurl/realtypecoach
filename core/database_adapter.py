"""Database adapter abstraction layer for RealTypeCoach.

Provides a pluggable backend system for different database implementations
(SQLite, PostgreSQL, etc.) while maintaining a consistent interface.
"""

import logging
from abc import ABC, abstractmethod
from contextlib import contextmanager

from core.models import (
    BurstTimeSeries,
    DailySummaryDB,
    DigraphPerformance,
    KeyPerformance,
    WordStatisticsLite,
)

log = logging.getLogger("realtypecoach.database_adapter")


class DatabaseAdapter(ABC):
    """Abstract base class for database adapters.

    All database backends must implement this interface to ensure
    compatibility with the Storage layer.
    """

    @abstractmethod
    def initialize(self) -> None:
        """Initialize database schema and perform migrations.

        This method should create all necessary tables and run any
        pending migrations.
        """
        pass

    @abstractmethod
    @contextmanager
    def get_connection(self):
        """Get a database connection.

        Yields:
            Database connection object (type varies by backend)
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Close all database connections and cleanup resources."""
        pass

    # ========== Burst Operations ==========

    @abstractmethod
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
        """Store a burst record.

        Args:
            start_time: Burst start timestamp (milliseconds since epoch)
            end_time: Burst end timestamp (milliseconds since epoch)
            key_count: Total keystrokes in burst
            backspace_count: Number of backspace keystrokes
            net_key_count: keystrokes minus backspaces
            duration_ms: Burst duration in milliseconds
            avg_wpm: Average words per minute
            qualifies_for_high_score: Whether burst qualifies for high score
        """
        pass

    @abstractmethod
    def get_bursts_for_timeseries(self, start_ms: int, end_ms: int) -> list[BurstTimeSeries]:
        """Get burst data for time-series graph.

        Args:
            start_ms: Start timestamp (milliseconds since epoch)
            end_ms: End timestamp (milliseconds since epoch)

        Returns:
            List of BurstTimeSeries models
        """
        pass

    @abstractmethod
    def get_burst_wpm_histogram(self, bin_count: int = 50) -> list[tuple[float, int]]:
        """Get burst WPM distribution as histogram data.

        Args:
            bin_count: Number of histogram bins

        Returns:
            List of (bin_center_wpm, count) tuples
        """
        pass

    @abstractmethod
    def get_recent_bursts(self, limit: int = 3) -> list[tuple[int, float, int, int, int, int, str]]:
        """Get the most recent bursts.

        Args:
            limit: Maximum number of bursts to return

        Returns:
            List of tuples: (id, wpm, net_chars, duration_ms, backspaces, start_time_ms, time_str)
        """
        pass

    @abstractmethod
    def get_burst_duration_stats_ms(self) -> tuple[int, int, int, int]:
        """Get burst duration statistics across all bursts.

        Returns:
            Tuple of (average_ms, min_ms, max_ms, percentile_95_ms)
        """
        pass

    @abstractmethod
    def get_burst_stats_for_date_range(self, start_ms: int, end_ms: int) -> tuple[int, int]:
        """Get burst statistics for a date range.

        Args:
            start_ms: Start timestamp (milliseconds since epoch)
            end_ms: End timestamp (milliseconds since epoch)

        Returns:
            Tuple of (total_keystrokes, total_bursts)
        """
        pass

    @abstractmethod
    def get_burst_wpms_for_threshold(self, start_ms: int, min_duration_ms: int) -> list[float]:
        """Get burst WPMS for threshold calculation.

        Args:
            start_ms: Start timestamp (milliseconds since epoch)
            min_duration_ms: Minimum burst duration in milliseconds

        Returns:
            List of WPM values (sorted ascending)
        """
        pass

    @abstractmethod
    def get_total_burst_duration(self, start_ms: int, end_ms: int) -> int:
        """Get total burst duration for a date range.

        Args:
            start_ms: Start timestamp (milliseconds since epoch)
            end_ms: End timestamp (milliseconds since epoch)

        Returns:
            Total duration in milliseconds
        """
        pass

    @abstractmethod
    def get_typing_time_by_granularity(
        self,
        granularity: str,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 90,
    ) -> list:
        """Get typing time aggregated by time granularity.

        Args:
            granularity: Time period granularity ("day", "week", "month", "quarter")
            start_date: Optional start date (YYYY-MM-DD)
            end_date: Optional end date (YYYY-MM-DD)
            limit: Maximum number of periods to return

        Returns:
            List of TypingTimeDataPoint models
        """
        pass

    # ========== Key Statistics Operations ==========

    @abstractmethod
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
        pass

    @abstractmethod
    def get_slowest_keys(self, limit: int = 10, layout: str | None = None) -> list[KeyPerformance]:
        """Get slowest keys (highest average press time).

        Args:
            limit: Maximum number of keys to return
            layout: Filter by layout (None for all layouts)

        Returns:
            List of KeyPerformance models
        """
        pass

    @abstractmethod
    def get_fastest_keys(self, limit: int = 10, layout: str | None = None) -> list[KeyPerformance]:
        """Get fastest keys (lowest average press time).

        Args:
            limit: Maximum number of keys to return
            layout: Filter by layout (None for all layouts)

        Returns:
            List of KeyPerformance models
        """
        pass

    # ========== Digraph Statistics Operations ==========

    @abstractmethod
    def update_digraph_statistics(
        self,
        first_keycode: int,
        second_keycode: int,
        first_key: str,
        second_key: str,
        layout: str,
        interval_ms: float,
    ) -> None:
        """Update statistics for a digraph (two-key combination).

        Args:
            first_keycode: Linux evdev keycode of first key
            second_keycode: Linux evdev keycode of second key
            first_key: First key character
            second_key: Second key character
            layout: Keyboard layout identifier
            interval_ms: Time between the two keys
        """
        pass

    @abstractmethod
    def get_slowest_digraphs(
        self, limit: int = 10, layout: str | None = None
    ) -> list[DigraphPerformance]:
        """Get slowest digraphs (highest average interval).

        Args:
            limit: Maximum number of digraphs to return
            layout: Filter by layout (None for all layouts)

        Returns:
            List of DigraphPerformance models
        """
        pass

    @abstractmethod
    def get_fastest_digraphs(
        self, limit: int = 10, layout: str | None = None
    ) -> list[DigraphPerformance]:
        """Get fastest digraphs (lowest average interval).

        Args:
            limit: Maximum number of digraphs to return
            layout: Filter by layout (None for all layouts)

        Returns:
            List of DigraphPerformance models
        """
        pass

    # ========== Word Statistics Operations ==========

    @abstractmethod
    def update_word_statistics(
        self,
        word: str,
        layout: str,
        duration_ms: int,
        num_letters: int,
        backspace_count: int = 0,
        editing_time_ms: int = 0,
        active_duration_ms: int = 0,
    ) -> None:
        """Update statistics for a word.

        Args:
            word: The word that was typed
            layout: Keyboard layout identifier
            duration_ms: Time taken to type the word (ms)
            num_letters: Number of letters in the word
            backspace_count: Number of backspaces used
            editing_time_ms: Time spent editing with backspace (ms)
            active_duration_ms: Active typing time excluding long pauses (ms)
        """
        pass

    @abstractmethod
    def get_slowest_words(
        self, limit: int = 10, layout: str | None = None
    ) -> list[WordStatisticsLite]:
        """Get slowest words (highest average time per letter).

        Args:
            limit: Maximum number of words to return
            layout: Filter by layout (None for all layouts)

        Returns:
            List of WordStatisticsLite models
        """
        pass

    @abstractmethod
    def get_fastest_words(
        self, limit: int = 10, layout: str | None = None
    ) -> list[WordStatisticsLite]:
        """Get fastest words (lowest average time per letter).

        Args:
            limit: Maximum number of words to return
            layout: Filter by layout (None for all layouts)

        Returns:
            List of WordStatisticsLite models
        """
        pass

    @abstractmethod
    def delete_words_by_list(self, words: list[str]) -> int:
        """Delete word statistics for words in the given list.

        Args:
            words: List of words (lowercase) to delete

        Returns:
            Number of rows deleted
        """
        pass

    @abstractmethod
    def get_all_word_statistics_words(self) -> list[str]:
        """Get all words currently stored in word_statistics.

        Returns:
            List of all words (lowercase)
        """
        pass

    # ========== Ignored Words Operations ==========

    @abstractmethod
    def add_ignored_word(self, word_hash: str, timestamp_ms: int) -> bool:
        """Add ignored word hash to database.

        Args:
            word_hash: BLAKE2b-256 hash of the word (64 hex chars)
            timestamp_ms: When the word was added (milliseconds since epoch)

        Returns:
            True if word was added, False if already exists
        """
        pass

    @abstractmethod
    def is_word_ignored(self, word_hash: str) -> bool:
        """Check if word hash is in ignored list.

        Args:
            word_hash: BLAKE2b-256 hash of the word (64 hex chars)

        Returns:
            True if word is ignored, False otherwise
        """
        pass

    @abstractmethod
    def get_all_ignored_word_hashes(self) -> list[dict]:
        """Get all ignored word hashes for sync.

        Returns:
            List of dicts with keys: word_hash, added_at
        """
        pass

    # ========== High Score Operations ==========

    @abstractmethod
    def store_high_score(self, date: str, wpm: float, duration_ms: int, key_count: int) -> None:
        """Store a high score for a date.

        Args:
            date: Date string (YYYY-MM-DD)
            wpm: Words per minute achieved
            duration_ms: Burst duration in milliseconds
            key_count: Number of keystrokes
        """
        pass

    @abstractmethod
    def get_today_high_score(self, date: str) -> float | None:
        """Get today's highest WPM.

        Args:
            date: Date string (YYYY-MM-DD)

        Returns:
            WPM or None if no bursts today
        """
        pass

    @abstractmethod
    def get_all_time_high_score(self) -> float | None:
        """Get all-time highest WPM.

        Returns:
            WPM or None if no bursts recorded
        """
        pass

    # ========== Daily Summary Operations ==========

    @abstractmethod
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
        pass

    @abstractmethod
    def get_daily_summary(self, date: str) -> DailySummaryDB | None:
        """Get daily summary for a date.

        Args:
            date: Date string (YYYY-MM-DD)

        Returns:
            DailySummaryDB model or None if not found
        """
        pass

    @abstractmethod
    def mark_summary_sent(self, date: str) -> None:
        """Mark daily summary as sent.

        Args:
            date: Date string (YYYY-MM-DD)
        """
        pass

    # ========== All-Time Statistics ==========

    @abstractmethod
    def get_all_time_typing_time(self, exclude_today: str | None = None) -> int:
        """Get all-time total typing time.

        Args:
            exclude_today: Optional date string (YYYY-MM-DD) to exclude

        Returns:
            Total typing time in seconds
        """
        pass

    @abstractmethod
    def get_today_typing_time(self, date: str) -> int:
        """Get typing time for a specific date.

        Args:
            date: Date string (YYYY-MM-DD)

        Returns:
            Typing time in milliseconds for the given date
        """
        pass

    @abstractmethod
    def get_all_time_keystrokes_and_bursts(
        self, exclude_today: str | None = None
    ) -> tuple[int, int]:
        """Get all-time total keystrokes and bursts.

        Args:
            exclude_today: Optional date string (YYYY-MM-DD) to exclude

        Returns:
            Tuple of (total_keystrokes, total_bursts)
        """
        pass

    @abstractmethod
    def get_average_burst_wpm(self) -> float | None:
        """Get long-term average WPM across all recorded bursts.

        Returns:
            Average WPM or None if no bursts recorded
        """
        pass

    @abstractmethod
    def get_all_burst_wpms_ordered(self) -> list[float]:
        """Get all burst WPM values ordered by time.

        Returns:
            List of WPM values ordered by start_time
        """
        pass

    @abstractmethod
    def get_burst_wpm_percentile(self, percentile: float) -> float | None:
        """Get WPM value at a given percentile across all bursts.

        Args:
            percentile: Percentile value (0-100), e.g., 95 for 95th percentile

        Returns:
            WPM value at the percentile or None if no bursts recorded
        """
        pass

    # ========== Data Management ==========

    @abstractmethod
    def delete_old_data(self, retention_days: int) -> None:
        """Delete data older than retention period.

        Args:
            retention_days: Number of days to keep, or -1 to keep forever
        """
        pass

    @abstractmethod
    def clear_database(self) -> None:
        """Clear all data from database."""
        pass

    @abstractmethod
    def export_to_csv(self, file_path, start_date: str) -> int:
        """Export data to CSV file.

        Args:
            file_path: Path to output CSV file
            start_date: Start date for export (YYYY-MM-DD)

        Returns:
            Number of rows exported
        """
        pass

    # ========== Sync Log Operations ==========

    @abstractmethod
    def insert_sync_log(self, entry: dict) -> int:
        """Insert a sync log entry.

        Args:
            entry: Dictionary with keys: timestamp, machine_name, pushed, pulled,
                   merged, duration_ms, error, table_breakdown

        Returns:
            Inserted record ID
        """
        pass

    @abstractmethod
    def get_sync_logs(self, limit: int = 100) -> list[dict]:
        """Get sync log entries (most recent first).

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of sync log dictionaries
        """
        pass

    @abstractmethod
    def get_sync_log_stats(self) -> dict:
        """Get aggregate sync log statistics.

        Returns:
            Dictionary with keys: total_syncs, total_pushed, total_pulled,
            total_merged, last_sync
        """
        pass


class AdapterError(Exception):
    """Base exception for database adapter errors."""

    pass


class ConnectionError(AdapterError):
    """Exception raised when database connection fails."""

    pass


class QueryError(AdapterError):
    """Exception raised when a database query fails."""

    pass
