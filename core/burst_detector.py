"""Burst detection for continuous typing periods."""

import time
from typing import Callable, Optional, List
from dataclasses import dataclass, field


@dataclass
class Burst:
    """Represents a burst of continuous typing."""
    start_time_ms: int
    end_time_ms: int = 0
    key_count: int = 0
    duration_ms: int = 0
    qualifies_for_high_score: bool = False
    key_timestamps_ms: List[int] = field(default_factory=list)


class BurstDetector:
    """Detects bursts of continuous typing."""

    def __init__(self, burst_timeout_ms: int = 1000,
                 high_score_min_duration_ms: int = 10000,
                 duration_calculation_method: str = 'total_time',
                 active_time_threshold_ms: int = 500,
                 min_key_count: int = 10,
                 min_duration_ms: int = 5000,
                 on_burst_complete: Optional[Callable[[Burst], None]] = None):
        """Initialize burst detector.

        Args:
            burst_timeout_ms: Maximum pause between keystrokes before burst ends (default: 1000ms)
            high_score_min_duration_ms: Minimum duration for burst to qualify for high score (default: 10000ms)
            duration_calculation_method: How to calculate burst duration - 'total_time' or 'active_time' (default: 'total_time')
            active_time_threshold_ms: For 'active_time' method, max interval to count as active (default: 500ms)
            min_key_count: Minimum keystrokes required for burst to be recorded (default: 10)
            min_duration_ms: Minimum duration required for burst to be recorded (default: 5000ms)
            on_burst_complete: Callback function called when burst completes
        """
        self.burst_timeout_ms = burst_timeout_ms
        self.high_score_min_duration_ms = high_score_min_duration_ms
        self.duration_calculation_method = duration_calculation_method
        self.active_time_threshold_ms = active_time_threshold_ms
        self.min_key_count = min_key_count
        self.min_duration_ms = min_duration_ms
        self.on_burst_complete = on_burst_complete
        self.current_burst: Optional[Burst] = None
        self.last_key_time_ms: Optional[int] = None

    def process_key_event(self, timestamp_ms: int, is_press: bool) -> Optional[Burst]:
        """Process a key event and detect bursts.

        Args:
            timestamp_ms: Timestamp of key event in milliseconds since epoch
            is_press: True if key press, False if release

        Returns:
            Completed Burst if a burst ended, None otherwise
        """
        if not is_press:
            return None

        if self.last_key_time_ms is None:
            self.last_key_time_ms = timestamp_ms
            self.current_burst = Burst(
                start_time_ms=timestamp_ms,
                end_time_ms=timestamp_ms,
                key_count=1,
                duration_ms=0,
                key_timestamps_ms=[timestamp_ms]
            )
            return None

        time_since_last = timestamp_ms - self.last_key_time_ms

        if time_since_last > self.burst_timeout_ms:
            return self._complete_burst(timestamp_ms)
        else:
            if self.current_burst:
                self.current_burst.key_count += 1
                self.current_burst.end_time_ms = timestamp_ms
                self.current_burst.key_timestamps_ms.append(timestamp_ms)
                self.current_burst.duration_ms = self._calculate_duration()
            self.last_key_time_ms = timestamp_ms
            return None

    def _complete_burst(self, timestamp_ms: int) -> Optional[Burst]:
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
                self.current_burst.key_count >= self.min_key_count and
                self.current_burst.duration_ms >= self.min_duration_ms
            )

            if meets_min_criteria:
                self.current_burst.qualifies_for_high_score = (
                    self.current_burst.duration_ms >= self.high_score_min_duration_ms
                )
                completed_burst = self.current_burst

                if self.on_burst_complete:
                    try:
                        self.on_burst_complete(completed_burst)
                    except Exception as e:
                        print(f"Error in burst complete callback: {e}")

        self.current_burst = Burst(
            start_time_ms=timestamp_ms,
            end_time_ms=timestamp_ms,
            key_count=1,
            duration_ms=0,
            key_timestamps_ms=[timestamp_ms]
        )
        self.last_key_time_ms = timestamp_ms

        return completed_burst

    def _calculate_duration(self) -> int:
        """Calculate burst duration based on configured method.

        Returns:
            Duration in milliseconds
        """
        if not self.current_burst or len(self.current_burst.key_timestamps_ms) < 2:
            return 0

        if self.duration_calculation_method == 'active_time':
            return self._calculate_active_time_duration()
        else:  # 'total_time'
            return self._calculate_total_time_duration()

    def _calculate_total_time_duration(self) -> int:
        """Calculate duration as total time from first to last key.

        Returns:
            Duration in milliseconds
        """
        return self.current_burst.end_time_ms - self.current_burst.start_time_ms

    def _calculate_active_time_duration(self) -> int:
        """Calculate duration as sum of intervals between keys < threshold.

        Only counts intervals between consecutive keystrokes that are
        shorter than active_time_threshold_ms. Longer gaps are excluded.

        Returns:
            Duration in milliseconds
        """
        timestamps = self.current_burst.key_timestamps_ms
        active_duration = 0

        for i in range(1, len(timestamps)):
            interval = timestamps[i] - timestamps[i-1]
            if interval <= self.active_time_threshold_ms:
                active_duration += interval

        return active_duration

    def get_current_burst_info(self) -> Optional[dict]:
        """Get information about current active burst.

        Returns:
            Dictionary with burst info or None if no active burst
        """
        if not self.current_burst:
            return None

        return {
            'key_count': self.current_burst.key_count,
            'duration_ms': self.current_burst.duration_ms,
            'duration_sec': self.current_burst.duration_ms / 1000.0,
            'qualifies': self.current_burst.qualifies_for_high_score,
        }

    def reset(self) -> None:
        """Reset burst detector state."""
        self.current_burst = None
        self.last_key_time_ms = None
