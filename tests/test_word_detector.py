"""Tests for WordDetector with correction window."""

from core.word_detector import WordDetector, WordState


class TestWordDetector:
    """Tests for WordDetector class."""

    def test_immediate_backspace_counts_as_editing_time(self):
        """Test that immediate backspace counts as editing time."""
        detector = WordDetector(max_correction_window_ms=3000)

        # Type "hello"
        result = detector.process_keystroke("h", 1000, is_letter=True, keycode=36)
        assert result is None

        result = detector.process_keystroke("e", 1100, is_letter=True, keycode=37)
        assert result is None

        result = detector.process_keystroke("l", 1200, is_letter=True, keycode=38)
        assert result is None

        result = detector.process_keystroke("l", 1300, is_letter=True, keycode=38)
        assert result is None

        result = detector.process_keystroke("o", 1400, is_letter=True, keycode=39)
        assert result is None

        # Backspace within 3 seconds - should count as editing time
        result = detector.process_keystroke("BACKSPACE", 2000, is_letter=False)
        assert result is None

        result = detector.process_keystroke("o", 2100, is_letter=True, keycode=39)
        assert result is None

        # Finalize word with space
        result = detector.process_keystroke("SPACE", 2200, is_letter=False)

        assert result is not None
        assert result.word == "hello"
        assert result.backspace_count == 1
        # Editing time should include the gap between 1400 and 2000 (600ms)
        assert result.editing_time_ms == 600

    def test_late_backspace_does_not_count_as_editing_time(self):
        """Test that backspace after correction window doesn't count as editing time."""
        detector = WordDetector(max_correction_window_ms=3000)

        # Type "hello"
        result = detector.process_keystroke("h", 1000, is_letter=True, keycode=36)
        assert result is None

        result = detector.process_keystroke("e", 1100, is_letter=True, keycode=37)
        assert result is None

        result = detector.process_keystroke("l", 1200, is_letter=True, keycode=38)
        assert result is None

        result = detector.process_keystroke("l", 1300, is_letter=True, keycode=38)
        assert result is None

        result = detector.process_keystroke("o", 1400, is_letter=True, keycode=39)
        assert result is None

        # Wait 5 seconds (exceeds 3 second window)
        # Backspace after window - should NOT count as editing time
        result = detector.process_keystroke("BACKSPACE", 6400, is_letter=False)
        assert result is None

        result = detector.process_keystroke("o", 6500, is_letter=True, keycode=39)
        assert result is None

        # Finalize word with space
        result = detector.process_keystroke("SPACE", 6600, is_letter=False)

        assert result is not None
        assert result.word == "hello"
        assert result.backspace_count == 1
        # Editing time should be 0 since the gap (1400 to 6400 = 5000ms) exceeds window
        assert result.editing_time_ms == 0

    def test_multiple_backspaces_mixed_timing(self):
        """Test multiple backspaces with some within and some outside window."""
        detector = WordDetector(max_correction_window_ms=3000)

        # Type "hello"
        result = detector.process_keystroke("h", 1000, is_letter=True, keycode=36)
        assert result is None

        result = detector.process_keystroke("e", 1100, is_letter=True, keycode=37)
        assert result is None

        result = detector.process_keystroke("l", 1200, is_letter=True, keycode=38)
        assert result is None

        result = detector.process_keystroke("l", 1300, is_letter=True, keycode=38)
        assert result is None

        result = detector.process_keystroke("o", 1400, is_letter=True, keycode=39)
        assert result is None

        # First backspace within window (600ms gap)
        result = detector.process_keystroke("BACKSPACE", 2000, is_letter=False)
        assert result is None

        # Second backspace also within window (100ms gap)
        result = detector.process_keystroke("BACKSPACE", 2100, is_letter=False)
        assert result is None

        # Type letters again
        result = detector.process_keystroke("l", 2200, is_letter=True, keycode=38)
        assert result is None

        result = detector.process_keystroke("o", 2300, is_letter=True, keycode=39)
        assert result is None

        # Third backspace within window (100ms gap)
        result = detector.process_keystroke("BACKSPACE", 2400, is_letter=False)
        assert result is None

        result = detector.process_keystroke("o", 2500, is_letter=True, keycode=39)
        assert result is None

        # Wait and then backspace after window (5000ms gap)
        result = detector.process_keystroke("BACKSPACE", 7500, is_letter=False)
        assert result is None

        result = detector.process_keystroke("o", 7600, is_letter=True, keycode=39)
        assert result is None

        # Finalize word with space
        result = detector.process_keystroke("SPACE", 7700, is_letter=False)

        assert result is not None
        assert result.word == "hello"
        assert result.backspace_count == 4
        # Editing time should only include the first three backspaces (600 + 100 + 100 = 800ms)
        # The last backspace gap (2500 to 7500 = 5000ms) should be excluded
        assert result.editing_time_ms == 800

    def test_custom_correction_window(self):
        """Test WordDetector with custom correction window."""
        detector = WordDetector(max_correction_window_ms=5000)

        # Type "test"
        result = detector.process_keystroke("t", 1000, is_letter=True, keycode=36)
        assert result is None

        result = detector.process_keystroke("e", 1100, is_letter=True, keycode=37)
        assert result is None

        result = detector.process_keystroke("s", 1200, is_letter=True, keycode=38)
        assert result is None

        result = detector.process_keystroke("t", 1300, is_letter=True, keycode=39)
        assert result is None

        # Backspace within 5 second window (4 second gap)
        result = detector.process_keystroke("BACKSPACE", 5300, is_letter=False)
        assert result is None

        result = detector.process_keystroke("t", 5400, is_letter=True, keycode=39)
        assert result is None

        # Finalize word
        result = detector.process_keystroke("SPACE", 5500, is_letter=False)

        assert result is not None
        assert result.word == "test"
        assert result.backspace_count == 1
        # With 5 second window, this should count as editing time
        assert result.editing_time_ms == 4000


class TestWordState:
    """Tests for WordState class."""

    def test_wordstate_max_correction_window_default(self):
        """Test that WordState has default correction window."""
        state = WordState(start_time_ms=1000, layout="us")
        assert state.max_correction_window_ms == 3000

    def test_wordstate_max_correction_window_custom(self):
        """Test that WordState can have custom correction window."""
        state = WordState(
            start_time_ms=1000, layout="us", max_correction_window_ms=5000
        )
        assert state.max_correction_window_ms == 5000

    def test_wordstate_handle_backspace_within_window(self):
        """Test WordState.handle_backspace within correction window."""
        state = WordState(
            start_time_ms=1000, layout="us", max_correction_window_ms=3000
        )
        state.word = "hello"
        state.last_keystroke_time_ms = 2000

        state.handle_backspace(2500)

        assert state.word == "hell"
        assert state.backspace_count == 1
        assert state.editing_time_ms == 500  # 2500 - 2000

    def test_wordstate_handle_backspace_outside_window(self):
        """Test WordState.handle_backspace outside correction window."""
        state = WordState(
            start_time_ms=1000, layout="us", max_correction_window_ms=3000
        )
        state.word = "hello"
        state.last_keystroke_time_ms = 2000

        # Backspace after 10 seconds (exceeds 3 second window)
        state.handle_backspace(12000)

        assert state.word == "hell"
        assert state.backspace_count == 1
        assert state.editing_time_ms == 0  # Gap too large, not counted

    def test_wordstate_reset_with_correction_window(self):
        """Test WordState.reset() with correction window parameter."""
        state = WordState(start_time_ms=1000, layout="us")
        state.word = "test"
        state.editing_time_ms = 500

        state.reset(5000, layout="us", max_correction_window_ms=5000)

        assert state.word == ""
        assert state.editing_time_ms == 0
        assert state.max_correction_window_ms == 5000
