"""Burst detection for continuous typing periods."""

import time
from typing import Callable, Optional
from dataclasses import dataclass


@dataclass
class Burst:
    """Represents a burst of continuous typing."""
    start_time_ms: int
    end_time_ms: int = 0
    key_count: int = 0
    duration_ms: int = 0
    qualifies_for_high_score: bool = False


class BurstDetector:
    """Detects bursts of continuous typing."""

    def __init__(self, burst_timeout_ms: int = 3000,
                 high_score_min_duration_ms: int = 10000,
                 on_burst_complete: Optional[Callable[[Burst], None]] = None):
        """Initialize burst detector.

        Args:
            burst_timeout_ms: Maximum pause between keystrokes before burst ends (default: 3000ms)
            high_score_min_duration_ms: Minimum duration for burst to qualify for high score (default: 10000ms)
            on_burst_complete: Callback function called when burst completes
        """
        self.burst_timeout_ms = burst_timeout_ms
        self.high_score_min_duration_ms = high_score_min_duration_ms
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
                duration_ms=0
            )
            return None

        time_since_last = timestamp_ms - self.last_key_time_ms

        if time_since_last > self.burst_timeout_ms:
            return self._complete_burst(timestamp_ms)
        else:
            if self.current_burst:
                self.current_burst.key_count += 1
                self.current_burst.end_time_ms = timestamp_ms
                self.current_burst.duration_ms = (
                    timestamp_ms - self.current_burst.start_time_ms
                )
            self.last_key_time_ms = timestamp_ms
            return None

    def _complete_burst(self, timestamp_ms: int) -> Optional[Burst]:
        """Complete current burst and start new one.

        Args:
            timestamp_ms: Timestamp of new key press

        Returns:
            Completed Burst object
        """
        completed_burst = None

        if self.current_burst and self.current_burst.key_count > 0:
            if self.last_key_time_ms is not None:
                self.current_burst.end_time_ms = self.last_key_time_ms
                self.current_burst.duration_ms = (
                    self.current_burst.end_time_ms - self.current_burst.start_time_ms
                )
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
            duration_ms=0
        )
        self.last_key_time_ms = timestamp_ms

        return completed_burst

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
