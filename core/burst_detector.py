"""Burst detection for continuous typing periods."""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.burst_config import BurstDetectorConfig, DurationCalculationMethod
from core.models import BurstInfo

if TYPE_CHECKING:
    from core.dictionary import Dictionary

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
    text_content: str = ""  # The actual text typed during this burst


class BurstDetector:
    """Detects bursts of continuous typing."""

    def __init__(
        self,
        config: BurstDetectorConfig,
        on_burst_complete: Callable[[Burst], None] | None = None,
        dictionary: "Dictionary | None" = None,
        language: str = "en",
    ):
        """Initialize burst detector.

        Args:
            config: BurstDetectorConfig object
            on_burst_complete: Callback function called when burst completes
            dictionary: Optional Dictionary instance for word validation
            language: Language code for word validation (default: "en")
        """
        self.config = config
        self.on_burst_complete = on_burst_complete
        self.dictionary = dictionary
        self.language = language
        self.current_burst: Burst | None = None
        self.last_key_time_ms: int | None = None
        self._current_timestamps: list[int] = []
        self._current_text: str = ""  # Track text content of current burst

    def process_key_event(
        self, timestamp_ms: int, is_press: bool, is_backspace: bool = False, key_name: str = ""
    ) -> Burst | None:
        """Process a key event and detect bursts.

        Args:
            timestamp_ms: Timestamp of key event in milliseconds since epoch
            is_press: True if key press, False if release
            is_backspace: True if key is backspace, False otherwise
            key_name: The character/key name (for text tracking)

        Returns:
            Completed Burst if a burst ended, None otherwise
        """
        if not is_press:
            return None

        # Track text content for validation
        self._update_text_content(key_name, is_backspace)

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
                backspace_ratio=float(backspace_count),  # 1.0 if backspace, 0.0 otherwise
                text_content=self._current_text,
            )
            return None

        time_since_last = timestamp_ms - self.last_key_time_ms

        if time_since_last > self.config.burst_timeout_ms:
            return self._complete_burst(timestamp_ms, is_backspace, key_name)
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
                        self.current_burst.backspace_count / self.current_burst.key_count
                    )
                self.current_burst.end_time_ms = timestamp_ms
                self._current_timestamps.append(timestamp_ms)
                self.current_burst.duration_ms = self._calculate_duration()
                self.current_burst.text_content = self._current_text
            self.last_key_time_ms = timestamp_ms
            return None

    def _complete_burst(self, timestamp_ms: int, is_backspace: bool = False, key_name: str = "") -> Burst | None:
        """Complete current burst and start new one.

        Args:
            timestamp_ms: Timestamp of new key press
            is_backspace: Whether the new key is backspace
            key_name: The character/key name for the new key

        Returns:
            Completed Burst object if it meets minimum criteria, None otherwise
        """
        completed_burst = None

        if self.current_burst and self.current_burst.key_count > 0:
            if self.last_key_time_ms is not None:
                self.current_burst.end_time_ms = self.last_key_time_ms
                self.current_burst.duration_ms = self._calculate_duration()
            
            # Update text content one final time
            self.current_burst.text_content = self._current_text

            # Check if burst meets minimum criteria for recording
            meets_min_criteria = (
                self.current_burst.key_count >= self.config.min_key_count
                and self.current_burst.duration_ms >= self.config.min_duration_ms
            )

            if meets_min_criteria:
                # Validate burst words before accepting
                if self._validate_burst_words(self.current_burst.text_content):
                    self.current_burst.qualifies_for_high_score = (
                        self.current_burst.duration_ms >= self.config.high_score_min_duration_ms
                    )
                    completed_burst = self.current_burst

                    if self.on_burst_complete:
                        try:
                            self.on_burst_complete(completed_burst)
                        except Exception as e:
                            log.error(f"Error in burst complete callback: {e}")
                else:
                    log.info(
                        f"Burst rejected by word validation: {self.current_burst.key_count} keys, "
                        f"{self.current_burst.duration_ms}ms, text: {self.current_burst.text_content[:50]}..."
                    )

        # Start new burst
        self._current_timestamps = [timestamp_ms]
        self._current_text = ""  # Reset text content for new burst
        
        # Process the new key for the new burst
        self._update_text_content(key_name, is_backspace)
        
        backspace_count = 1 if is_backspace else 0
        self.current_burst = Burst(
            start_time_ms=timestamp_ms,
            end_time_ms=timestamp_ms,
            key_count=1,
            backspace_count=backspace_count,
            net_key_count=0 if is_backspace else 1,
            duration_ms=0,
            backspace_ratio=float(backspace_count),  # 1.0 if backspace, 0.0 otherwise
            text_content=self._current_text,
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

        if self.config.duration_calculation_method == DurationCalculationMethod.ACTIVE_TIME:
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

    def _update_text_content(self, key_name: str, is_backspace: bool) -> None:
        """Update the current text content based on key press.

        Args:
            key_name: The character/key name
            is_backspace: True if key is backspace
        """
        if is_backspace:
            # Remove last character on backspace
            if len(self._current_text) > 0:
                self._current_text = self._current_text[:-1]
        else:
            # Only append printable characters (letters, numbers, punctuation, spaces)
            # Skip special keys like SHIFT, CTRL, ALT, etc.
            if key_name and len(key_name) == 1:
                # Single character - append it
                self._current_text += key_name
            elif key_name == "SPACE":
                self._current_text += " "
            elif key_name in ("ENTER", "KPENTER", "RETURN"):
                self._current_text += "\n"
            elif key_name == "TAB":
                self._current_text += "\t"
            # Other special keys are ignored for text tracking

    def _validate_burst_words(self, text: str) -> bool:
        """Validate that the burst text contains valid words.

        Args:
            text: The text content of the burst

        Returns:
            True if burst passes validation, False otherwise
        """
        # If word validation is disabled, always pass
        if not self.config.validate_burst_words:
            return True

        # If no dictionary available, we can't validate - accept by default
        if self.dictionary is None:
            return True

        # Extract words from text (split on whitespace and punctuation)
        # Use regex to find word-like sequences
        words = re.findall(r'[a-zA-Z]{%d,}' % self.config.burst_min_word_length, text)
        
        if not words:
            # No words found - if there's text but no valid words, it might be gibberish
            # Accept if text is short (might be just numbers/symbols)
            # Reject if text is long but has no valid words
            if len(text) > self.config.min_key_count * 2:
                log.debug(f"Burst rejected: no valid words found in text of length {len(text)}")
                return False
            return True

        # Count valid words
        valid_count = 0
        for word in words:
            if self.dictionary.is_valid_word(word, self.language):
                valid_count += 1

        # Calculate validation ratio
        validation_ratio = valid_count / len(words)
        
        log.debug(f"Burst word validation: {valid_count}/{len(words)} words valid (ratio: {validation_ratio:.2f})")
        
        return validation_ratio >= self.config.burst_word_validation_threshold

    def get_current_burst_info(self) -> BurstInfo | None:
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
        self._current_text = ""
