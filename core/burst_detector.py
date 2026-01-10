"""Burst detection for continuous typing periods."""

import logging
from typing import Callable, Optional, List
from dataclasses import dataclass

from core.burst_config import BurstDetectorConfig, DurationCalculationMethod
from core.models import BurstInfo

log = logging.getLogger("realtypecoach.burst_detector")


@dataclass
class Burst:
    """Represents a burst of continuous typing."""

    start_time_ms: int
    end_time_ms: int = 0
    key_count: int = 0
    backspace_count: int = 0
    net_key_count: int = 0
    duration_ms: int = 0
    qualifies_for_high_score: bool = False
    backspace_ratio: float = 0.0


class BurstDetector:
    """Detects bursts of continuous typing."""

    def __init__(
        self,
        config: BurstDetectorConfig,
        on_burst_complete: Optional[Callable[[Burst], None]] = None,
    ):
        """Initialize burst detector.

        Args:
            config: BurstDetectorConfig object
            on_burst_complete: Callback function called when burst completes
        """
        self.config = config
        self.on_burst_complete = on_burst_complete
        self.current_burst: Optional[Burst] = None
        self.last_key_time_ms: Optional[int] = None
        self._current_timestamps: List[int] = []

    def process_key_event(
        self, timestamp_ms: int, is_press: bool, is_backspace: bool = False
    ) -> Optional[Burst]:
        """Process a key event and detect bursts.

        Args:
            timestamp_ms: Timestamp of key event in milliseconds since epoch
            is_press: True if key press, False if release
            is_backspace: True if key is backspace, False otherwise

        Returns:
            Completed Burst if a burst ended, None otherwise
        """
        if not is_press:
            return None

        if self.last_key_time_ms is None:
            self.last_key_time_ms = timestamp_ms
            self._current_timestamps = [timestamp_ms]
            backspace_count = 1 if is_backspace else 0
            self.current_burst = Burst(
                start_time_ms=timestamp_ms,
                end_time_ms=timestamp_ms,
                key_count=1,
                backspace_count=backspace_count,
                net_key_count=0 if is_backspace else 1,
                duration_ms=0,
                backspace_ratio=float(
                    backspace_count
                ),  # 1.0 if backspace, 0.0 otherwise
            )
            return None

        time_since_last = timestamp_ms - self.last_key_time_ms

        if time_since_last > self.config.burst_timeout_ms:
            return self._complete_burst(timestamp_ms, is_backspace)
        else:
            if self.current_burst:
                self.current_burst.key_count += 1
                if is_backspace:
                    self.current_burst.backspace_count += 1
                # Net characters: each backspace removes 1 character + the backspace itself = 2
                self.current_burst.net_key_count = self.current_burst.key_count - (
                    self.current_burst.backspace_count * 2
                )
                # Calculate backspace ratio
                if self.current_burst.key_count > 0:
                    self.current_burst.backspace_ratio = (
                        self.current_burst.backspace_count
                        / self.current_burst.key_count
                    )
                self.current_burst.end_time_ms = timestamp_ms
                self._current_timestamps.append(timestamp_ms)
                self.current_burst.duration_ms = self._calculate_duration()
            self.last_key_time_ms = timestamp_ms
            return None

    def _complete_burst(
        self, timestamp_ms: int, is_backspace: bool = False
    ) -> Optional[Burst]:
        """Complete current burst and start new one.

        Args:
            timestamp_ms: Timestamp of new key press

        Returns:
            Completed Burst object if it meets minimum criteria, None otherwise
        """
        completed_burst = None

        if self.current_burst and self.current_burst.key_count > 0:
            if self.last_key_time_ms is not None:
                self.current_burst.end_time_ms = self.last_key_time_ms
                self.current_burst.duration_ms = self._calculate_duration()

            # Check if burst meets minimum criteria for recording
            meets_min_criteria = (
                self.current_burst.key_count >= self.config.min_key_count
                and self.current_burst.duration_ms >= self.config.min_duration_ms
            )

            if meets_min_criteria:
                self.current_burst.qualifies_for_high_score = (
                    self.current_burst.duration_ms
                    >= self.config.high_score_min_duration_ms
                )
                completed_burst = self.current_burst

                if self.on_burst_complete:
                    try:
                        self.on_burst_complete(completed_burst)
                    except Exception as e:
                        log.error(f"Error in burst complete callback: {e}")

        self._current_timestamps = [timestamp_ms]
        backspace_count = 1 if is_backspace else 0
        self.current_burst = Burst(
            start_time_ms=timestamp_ms,
            end_time_ms=timestamp_ms,
            key_count=1,
            backspace_count=backspace_count,
            net_key_count=0 if is_backspace else 1,
            duration_ms=0,
            backspace_ratio=float(backspace_count),  # 1.0 if backspace, 0.0 otherwise
        )
        self.last_key_time_ms = timestamp_ms

        return completed_burst

    def _calculate_duration(self) -> int:
        """Calculate burst duration based on configured method.

        Returns:
            Duration in milliseconds
        """
        if not self.current_burst or len(self._current_timestamps) < 2:
            return 0

        if (
            self.config.duration_calculation_method
            == DurationCalculationMethod.ACTIVE_TIME
        ):
            return self._calculate_active_time_duration()
        else:  # TOTAL_TIME
            return self._calculate_total_time_duration()

    def _calculate_total_time_duration(self) -> int:
        """Calculate duration as total time from first to last key.

        Returns:
            Duration in milliseconds (non-negative)
        """
        duration = self.current_burst.end_time_ms - self.current_burst.start_time_ms
        return max(0, duration)

    def _calculate_active_time_duration(self) -> int:
        """Calculate duration as sum of intervals between keys < threshold.

        Only counts intervals between consecutive keystrokes that are
        shorter than active_time_threshold_ms. Longer gaps are excluded.

        Returns:
            Duration in milliseconds
        """
        timestamps = self._current_timestamps
        active_duration = 0

        for i in range(1, len(timestamps)):
            interval = timestamps[i] - timestamps[i - 1]
            if interval <= self.config.active_time_threshold_ms:
                active_duration += interval

        return active_duration

    def get_current_burst_info(self) -> Optional[BurstInfo]:
        """Get information about current active burst.

        Returns:
            BurstInfo or None if no active burst
        """
        if not self.current_burst:
            return None

        from core.models import BurstInfo

        return BurstInfo(
            key_count=self.current_burst.key_count,
            duration_ms=self.current_burst.duration_ms,
            qualifies=self.current_burst.qualifies_for_high_score,
        )

    def reset(self) -> None:
        """Reset burst detector state."""
        self.current_burst = None
        self.last_key_time_ms = None
        self._current_timestamps = []
