"""Word detection with backspace editing tracking."""

import logging
from dataclasses import dataclass, field
from typing import Optional, List

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
    keystrokes: List[KeystrokeInfo] = field(default_factory=list)
    backspace_count: int = field(default=0)
    editing_time_ms: int = field(default=0)
    layout: str = field(default="us")

    def add_keystroke(self, key_name: str, timestamp_ms: int) -> None:
        """Add a letter keystroke to current word.

        Args:
            key_name: Letter key name
            timestamp_ms: Timestamp of keystroke
        """
        self.word += key_name
        self.keystrokes.append(
            KeystrokeInfo(key=key_name, time=timestamp_ms, type="letter")
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
                self.editing_time_ms += time_since_last

            self.word = self.word[:-1]
            self.keystrokes.append(
                KeystrokeInfo(key="BACKSPACE", time=timestamp_ms, type="backspace")
            )
            self.last_keystroke_time_ms = timestamp_ms

    def finalize(self, end_time_ms: int) -> int:
        """Calculate total duration for this word.

        Args:
            end_time_ms: Timestamp when word was finalized (e.g., space pressed)

        Returns:
            Total duration in milliseconds from start to end
        """
        return end_time_ms - self.start_time_ms

    def reset(self, start_time_ms: int, layout: str = "us") -> None:
        """Reset word state for new word.

        Args:
            start_time_ms: Timestamp of first keystroke for new word
            layout: Keyboard layout
        """
        self.word = ""
        self.start_time_ms = start_time_ms
        self.last_keystroke_time_ms = start_time_ms
        self.keystrokes = []
        self.backspace_count = 0
        self.editing_time_ms = 0
        self.layout = layout


class WordDetector:
    """Detects words and tracks backspace editing."""

    def __init__(self, word_boundary_timeout_ms: int = 1000, min_word_length: int = 3):
        """Initialize word detector.

        Args:
            word_boundary_timeout_ms: Max pause before word splits (ms)
            min_word_length: Minimum letters for a word to be stored
        """
        self.word_boundary_timeout_ms = word_boundary_timeout_ms
        self.min_word_length = min_word_length
        self.current_state: Optional[WordState] = None

    def process_keystroke(
        self,
        key_name: str,
        timestamp_ms: int,
        layout: str = "us",
        is_letter: bool = False,
    ) -> Optional[WordInfo]:
        """Process a keystroke and return word info if finalized.

        Args:
            key_name: Key name (letter or special key)
            timestamp_ms: Timestamp in milliseconds
            layout: Keyboard layout
            is_letter: Whether key is a letter key

        Returns:
            WordInfo if word was finalized, None otherwise
        """
        if is_letter:
            return self._process_letter(key_name, timestamp_ms, layout)
        elif key_name == "BACKSPACE":
            return self._process_backspace(timestamp_ms)
        else:
            return self._process_boundary(key_name, timestamp_ms)

    def _process_letter(
        self, key_name: str, timestamp_ms: int, layout: str
    ) -> Optional[WordInfo]:
        """Process letter keystroke.

        Args:
            key_name: Letter key name
            timestamp_ms: Timestamp
            layout: Keyboard layout

        Returns:
            WordInfo if timeout triggered and existing word finalized, None otherwise
        """
        if not self.current_state:
            self.current_state = WordState(start_time_ms=timestamp_ms, layout=layout)
            self.current_state.add_keystroke(key_name, timestamp_ms)
            return None

        state = self.current_state

        if state.last_keystroke_time_ms > 0:
            pause = timestamp_ms - state.last_keystroke_time_ms

            if pause > self.word_boundary_timeout_ms:
                finalized = self._finalize_current_state()
                self.current_state = WordState(
                    start_time_ms=timestamp_ms, layout=layout
                )
                self.current_state.add_keystroke(key_name, timestamp_ms)
                return finalized

        state.add_keystroke(key_name, timestamp_ms)
        return None

    def _process_backspace(self, timestamp_ms: int) -> Optional[WordInfo]:
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

    def _process_boundary(self, key_name: str, timestamp_ms: int) -> Optional[WordInfo]:
        """Process word boundary keystroke (space, punctuation, etc.).

        Args:
            key_name: Boundary key name
            timestamp_ms: Timestamp

        Returns:
            WordInfo if word was finalized, None otherwise
        """
        if self.current_state:
            finalized = self._finalize_current_state(timestamp_ms)
            self.current_state = None
            return finalized

        return None

    def _finalize_current_state(
        self, end_time_ms: Optional[int] = None
    ) -> Optional[WordInfo]:
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

        return WordInfo(
            word=state.word,
            layout=state.layout,
            total_duration_ms=total_duration_ms,
            editing_time_ms=state.editing_time_ms,
            backspace_count=state.backspace_count,
            num_letters=len(state.word),
        )

    def reset(self) -> None:
        """Reset detector state."""
        self.current_state = None
