"""Word detection with backspace editing tracking."""

import logging
from dataclasses import dataclass, field

from core.models import KeystrokeInfo, WordInfo

log = logging.getLogger("realtypecoach.word_detector")


@dataclass
class WordState:
    """State tracking for a word being typed and edited.

    Tracks the complete typing history of a word including backspace edits.
    """

    word: str = field(default="")
    start_time_ms: int = field(default=0)
    last_keystroke_time_ms: int = field(default=0)
    keystrokes: list[KeystrokeInfo] = field(default_factory=list)
    backspace_count: int = field(default=0)
    editing_time_ms: int = field(default=0)
    layout: str = field(default="us")
    max_correction_window_ms: int = field(default=3000)

    def add_keystroke(self, key_name: str, timestamp_ms: int, keycode: int | None = None) -> None:
        """Add a letter keystroke to current word.

        Args:
            key_name: Letter key name
            timestamp_ms: Timestamp of keystroke
            keycode: Linux evdev keycode (optional)
        """
        self.word += key_name
        self.keystrokes.append(
            KeystrokeInfo(key=key_name, time=timestamp_ms, type="letter", keycode=keycode)
        )
        self.last_keystroke_time_ms = timestamp_ms

    def handle_backspace(self, timestamp_ms: int) -> None:
        """Handle backspace keystroke.

        Args:
            timestamp_ms: Timestamp of backspace keystroke
        """
        if self.word:
            self.backspace_count += 1

            if self.last_keystroke_time_ms > 0:
                time_since_last = timestamp_ms - self.last_keystroke_time_ms
                # Only count as editing time if within correction window
                if time_since_last <= self.max_correction_window_ms:
                    self.editing_time_ms += time_since_last

            self.word = self.word[:-1]
            self.keystrokes.append(
                KeystrokeInfo(key="BACKSPACE", time=timestamp_ms, type="backspace")
            )
            self.last_keystroke_time_ms = timestamp_ms

    def _calculate_active_duration(self, threshold_ms: int) -> int:
        """Calculate active typing duration from keystroke intervals.

        Only counts intervals between consecutive keystrokes that are
        shorter than threshold_ms. Longer gaps (thinking pauses) are excluded.

        Args:
            threshold_ms: Maximum interval to count as active typing (ms)

        Returns:
            Active typing duration in milliseconds
        """
        if len(self.keystrokes) < 2:
            return 0

        # Use only filtered keystrokes (letters, no backspaces)
        letter_keystrokes = [ks for ks in self.keystrokes if ks.type == "letter"]

        if len(letter_keystrokes) < 2:
            return 0

        active_duration = 0
        for i in range(1, len(letter_keystrokes)):
            interval = letter_keystrokes[i].time - letter_keystrokes[i - 1].time
            if interval <= threshold_ms:
                active_duration += interval

        return max(active_duration, 50 * len(letter_keystrokes))  # Minimum 50ms per letter

    def finalize(self, end_time_ms: int) -> int:
        """Calculate total duration for this word.

        Args:
            end_time_ms: Timestamp when word was finalized (e.g., space pressed)

        Returns:
            Total duration in milliseconds from start to end
        """
        return end_time_ms - self.start_time_ms

    def reset(
        self,
        start_time_ms: int,
        layout: str = "us",
        max_correction_window_ms: int = 3000,
    ) -> None:
        """Reset word state for new word.

        Args:
            start_time_ms: Timestamp of first keystroke for new word
            layout: Keyboard layout
            max_correction_window_ms: Max time for backspace to count as editing (ms)
        """
        self.word = ""
        self.start_time_ms = start_time_ms
        self.last_keystroke_time_ms = start_time_ms
        self.keystrokes = []
        self.backspace_count = 0
        self.editing_time_ms = 0
        self.layout = layout
        self.max_correction_window_ms = max_correction_window_ms


class WordDetector:
    """Detects words and tracks backspace editing."""

    def __init__(
        self,
        word_boundary_timeout_ms: int = 1000,
        min_word_length: int = 3,
        max_correction_window_ms: int = 3000,
        active_time_threshold_ms: int = 2000,
    ):
        """Initialize word detector.

        Args:
            word_boundary_timeout_ms: Max pause before word splits (ms)
            min_word_length: Minimum letters for a word to be stored
            max_correction_window_ms: Max time for backspace to count as editing (ms)
            active_time_threshold_ms: Max interval to count as active typing for word WPM (ms)
        """
        self.word_boundary_timeout_ms = word_boundary_timeout_ms
        self.min_word_length = min_word_length
        self.max_correction_window_ms = max_correction_window_ms
        self.active_time_threshold_ms = active_time_threshold_ms
        self.current_state: WordState | None = None

    def process_keystroke(
        self,
        key_name: str,
        timestamp_ms: int,
        layout: str = "us",
        is_letter: bool = False,
        keycode: int | None = None,
    ) -> WordInfo | None:
        """Process a keystroke and return word info if finalized.

        Args:
            key_name: Key name (letter or special key)
            timestamp_ms: Timestamp in milliseconds
            layout: Keyboard layout
            is_letter: Whether key is a letter key
            keycode: Linux evdev keycode (optional)

        Returns:
            WordInfo if word was finalized, None otherwise
        """
        if is_letter:
            return self._process_letter(key_name, timestamp_ms, layout, keycode)
        elif key_name == "BACKSPACE":
            return self._process_backspace(timestamp_ms)
        else:
            return self._process_boundary(key_name, timestamp_ms)

    def _process_letter(
        self, key_name: str, timestamp_ms: int, layout: str, keycode: int | None = None
    ) -> WordInfo | None:
        """Process letter keystroke.

        Args:
            key_name: Letter key name
            timestamp_ms: Timestamp
            layout: Keyboard layout
            keycode: Linux evdev keycode (optional)

        Returns:
            WordInfo if timeout triggered and existing word finalized, None otherwise
        """
        if not self.current_state:
            self.current_state = WordState(
                start_time_ms=timestamp_ms,
                layout=layout,
                max_correction_window_ms=self.max_correction_window_ms,
            )
            self.current_state.add_keystroke(key_name, timestamp_ms, keycode)
            return None

        state = self.current_state

        if state.last_keystroke_time_ms > 0:
            pause = timestamp_ms - state.last_keystroke_time_ms

            if pause > self.word_boundary_timeout_ms:
                finalized = self._finalize_current_state()
                self.current_state = WordState(
                    start_time_ms=timestamp_ms,
                    layout=layout,
                    max_correction_window_ms=self.max_correction_window_ms,
                )
                self.current_state.add_keystroke(key_name, timestamp_ms, keycode)
                return finalized

        state.add_keystroke(key_name, timestamp_ms, keycode)
        return None

    def _process_backspace(self, timestamp_ms: int) -> WordInfo | None:
        """Process backspace keystroke.

        Args:
            timestamp_ms: Timestamp

        Returns:
            WordInfo if word was backspaced completely and needs finalization
        """
        if not self.current_state:
            return None

        self.current_state.handle_backspace(timestamp_ms)

        if not self.current_state.word and self.current_state.backspace_count > 0:
            return self._finalize_current_state()

        return None

    def _process_boundary(self, key_name: str, timestamp_ms: int) -> WordInfo | None:
        """Process word boundary keystroke (space, punctuation, etc.).

        Args:
            key_name: Boundary key name
            timestamp_ms: Timestamp

        Returns:
            WordInfo if word was finalized, None otherwise
        """
        if self.current_state:
            # Use last keystroke time, not boundary key time, to avoid counting pre-space pause
            finalized = self._finalize_current_state(None)
            self.current_state = None
            return finalized

        return None

    def _filter_keystrokes_to_final_word(
        self, keystrokes: list[KeystrokeInfo], final_word: str
    ) -> list[KeystrokeInfo]:
        """Filter keystrokes to only include those contributing to the final word.

        Handles backspaces by tracking which keystrokes remain in the final word.
        Preserves original timing information for valid keystrokes.

        Args:
            keystrokes: Complete keystroke list including backspaces
            final_word: The final recognized word

        Returns:
            Filtered keystroke list with only final word characters
        """
        # Simulate typing to find which keystrokes contribute to final word
        temp_word = []
        preserved_keystrokes = []

        for ks in keystrokes:
            if ks.type == "letter":
                temp_word.append(ks.key)
                preserved_keystrokes.append(ks)
            elif ks.type == "backspace" and temp_word:
                temp_word.pop()
                preserved_keystrokes.append(ks)

        # Match preserved keystrokes to final word characters
        final_keystrokes = []
        word_idx = 0

        for ks in preserved_keystrokes:
            if ks.type == "letter":
                if word_idx < len(final_word) and ks.key == final_word[word_idx]:
                    final_keystrokes.append(ks)
                    word_idx += 1
            elif ks.type == "backspace":
                # Skip backspaces in final keystroke list
                continue

        return final_keystrokes

    def _finalize_current_state(self, end_time_ms: int | None = None) -> WordInfo | None:
        """Finalize current word state.

        Args:
            end_time_ms: End timestamp (if None, uses last keystroke time)

        Returns:
            WordInfo if word meets criteria, None otherwise
        """
        if not self.current_state:
            return None

        state = self.current_state

        if end_time_ms is None:
            end_time_ms = state.last_keystroke_time_ms

        if len(state.word) < self.min_word_length:
            return None

        total_duration_ms = state.finalize(end_time_ms)

        # Calculate active typing duration (excludes long pauses)
        active_duration_ms = state._calculate_active_duration(self.active_time_threshold_ms)

        # Filter keystrokes to only include those contributing to the final word
        filtered_keystrokes = self._filter_keystrokes_to_final_word(state.keystrokes, state.word)

        return WordInfo(
            word=state.word,
            layout=state.layout,
            total_duration_ms=total_duration_ms,
            active_duration_ms=active_duration_ms,
            editing_time_ms=state.editing_time_ms,
            backspace_count=state.backspace_count,
            num_letters=len(state.word),
            keystrokes=filtered_keystrokes,  # Include only filtered keystroke list
        )

    def reset(self) -> None:
        """Reset detector state."""
        self.current_state = None
