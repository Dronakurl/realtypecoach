"""Tests for BurstDetector class."""

import pytest

from core.burst_config import BurstDetectorConfig
from core.burst_detector import Burst, BurstDetector


class TestBurst:
    """Test Burst class."""

    def test_create_burst(self):
        """Test creating a burst."""
        burst = Burst(
            start_time_ms=1000,
            end_time_ms=6000,
            key_count=10,
            duration_ms=5000,
            qualifies_for_high_score=True,
        )

        assert burst.start_time_ms == 1000
        assert burst.end_time_ms == 6000
        assert burst.key_count == 10
        assert burst.duration_ms == 5000
        assert burst.qualifies_for_high_score

    def test_burst_duration_calculation(self):
        """Test that burst duration is calculated correctly."""
        burst = Burst(
            start_time_ms=1000,
            end_time_ms=6000,
            key_count=10,
            duration_ms=5000,
            qualifies_for_high_score=False,
        )

        # Duration should be 5000ms = 5 seconds
        assert burst.duration_ms == 5000


class TestBurstDetector:
    """Test BurstDetector class."""

    def test_init(self):
        """Test burst detector initialization."""
        burst_completed = []

        config = BurstDetectorConfig(
            burst_timeout_ms=3000,
            high_score_min_duration_ms=10000,
        )

        detector = BurstDetector(
            config=config,
            on_burst_complete=lambda b: burst_completed.append(b),
        )

        assert detector.config.burst_timeout_ms == 3000
        assert detector.config.high_score_min_duration_ms == 10000

    def test_single_keypress(self):
        """Test processing a single key press."""
        burst_completed = []

        config = BurstDetectorConfig(
            burst_timeout_ms=3000,
            high_score_min_duration_ms=10000,
        )

        detector = BurstDetector(
            config=config,
            on_burst_complete=lambda b: burst_completed.append(b),
        )

        # Process press and release
        detector.process_key_event(1000, True, False, "a")  # press 'a'
        result = detector.process_key_event(1500, False, False, "a")  # release 'a'

        # Should not complete a burst yet (waiting for timeout)
        assert result is None

    def test_burst_completion(self):
        """Test that burst completes after timeout."""
        burst_completed = []

        config = BurstDetectorConfig(
            burst_timeout_ms=3000,
            high_score_min_duration_ms=10000,
            min_key_count=2,  # Lower threshold for test
            min_duration_ms=1000,  # Lower threshold for test
        )

        detector = BurstDetector(
            config=config,
            on_burst_complete=lambda b: burst_completed.append(b),
        )

        # Process some key events
        detector.process_key_event(1000, True, False, "a")
        detector.process_key_event(1200, False, False, "a")
        detector.process_key_event(2000, True, False, "b")
        detector.process_key_event(2200, False, False, "b")

        # Trigger timeout (7800ms gap > 3000ms threshold)
        result = detector.process_key_event(10000, True, False, "c")  # Way past timeout

        assert result is not None
        assert isinstance(result, Burst)
        assert result.key_count == 2  # 2 key press events

    def test_high_score_qualification(self):
        """Test high score qualification."""
        burst_completed = []

        config = BurstDetectorConfig(
            burst_timeout_ms=3000,
            high_score_min_duration_ms=10000,  # 10 seconds minimum
            min_key_count=2,  # Lower threshold for test
            min_duration_ms=1000,  # Lower threshold for test
        )

        detector = BurstDetector(
            config=config,
            on_burst_complete=lambda b: burst_completed.append(b),
        )

        # Simulate a burst with less than 10 seconds duration but >1 second
        # Need 2 key presses to meet min_key_count
        detector.process_key_event(1000, True, False, "a")  # First key press
        detector.process_key_event(2100, True, False, "b")  # Second key press (1100ms later)

        # Complete the burst (timeout triggered)
        result = detector.process_key_event(10000, True, False, "c")

        assert result is not None
        assert not result.qualifies_for_high_score  # Too short (duration < 10000ms)

    def test_high_score_qualified(self):
        """Test that longer bursts qualify for high score."""
        burst_completed = []

        config = BurstDetectorConfig(
            burst_timeout_ms=3000,
            high_score_min_duration_ms=10000,  # 10 seconds minimum
            min_key_count=5,  # Lower threshold for test
            min_duration_ms=1000,  # Lower threshold for test
        )

        detector = BurstDetector(
            config=config,
            on_burst_complete=lambda b: burst_completed.append(b),
        )

        # Simulate a ~10.8 second burst (just key press events spread out)
        start_time = 1000
        for i in range(10):
            press_time = start_time + (i * 1200)
            release_time = press_time + 100
            detector.process_key_event(press_time, True, False, "a")
            detector.process_key_event(release_time, False, False, "a")

        # Complete the burst (timeout triggered)
        result = detector.process_key_event(start_time + 15000, True, False, "a")

        assert result is not None
        # Should qualify because duration > 10 seconds
        # (start_time to last event is > 10 seconds)
        assert result.qualifies_for_high_score

    def test_backspace_ratio_calculation(self):
        """Test that backspace ratio is calculated correctly."""
        burst_completed = []

        config = BurstDetectorConfig(
            burst_timeout_ms=3000,
            high_score_min_duration_ms=10000,
            min_key_count=5,
            min_duration_ms=1000,
        )

        detector = BurstDetector(
            config=config,
            on_burst_complete=lambda b: burst_completed.append(b),
        )

        # Simulate typing with 30% backspaces (13 total keys, 3 backspaces)
        detector.process_key_event(1000, True, is_backspace=False, key_name="a")  # 1
        detector.process_key_event(1200, True, is_backspace=False, key_name="b")  # 2
        detector.process_key_event(1400, True, is_backspace=True, key_name="BACKSPACE")  # backspace 1
        detector.process_key_event(1600, True, is_backspace=False, key_name="c")  # 3
        detector.process_key_event(1800, True, is_backspace=False, key_name="d")  # 4
        detector.process_key_event(2000, True, is_backspace=True, key_name="BACKSPACE")  # backspace 2
        detector.process_key_event(2200, True, is_backspace=False, key_name="e")  # 5
        detector.process_key_event(2400, True, is_backspace=False, key_name="f")  # 6
        detector.process_key_event(2600, True, is_backspace=False, key_name="g")  # 7
        detector.process_key_event(2800, True, is_backspace=True, key_name="BACKSPACE")  # backspace 3
        detector.process_key_event(3000, True, is_backspace=False, key_name="h")  # 8
        detector.process_key_event(3200, True, is_backspace=False, key_name="i")  # 9
        detector.process_key_event(3400, True, is_backspace=False, key_name="j")  # 10

        # Complete the burst
        result = detector.process_key_event(15000, True, False, "k")

        assert result is not None
        assert result.key_count == 13  # 13 total keys (including backspaces)
        assert result.backspace_count == 3
        assert result.backspace_ratio == pytest.approx(0.2308, rel=0.01)  # 3/13

    def test_backspace_ratio_zero_when_no_backspaces(self):
        """Test that backspace ratio is 0 when there are no backspaces."""
        burst_completed = []

        config = BurstDetectorConfig(
            burst_timeout_ms=3000,
            high_score_min_duration_ms=10000,
            min_key_count=5,
            min_duration_ms=1000,
        )

        detector = BurstDetector(
            config=config,
            on_burst_complete=lambda b: burst_completed.append(b),
        )

        # Simulate typing with no backspaces
        for i in range(10):
            detector.process_key_event(1000 + (i * 200), True, is_backspace=False, key_name="a")

        # Complete the burst
        result = detector.process_key_event(15000, True, False, "a")

        assert result is not None
        assert result.backspace_count == 0
        assert result.backspace_ratio == 0.0

    def test_backspace_ratio_with_all_backspaces(self):
        """Test that backspace ratio is 1.0 when all keys are backspaces."""
        burst_completed = []

        config = BurstDetectorConfig(
            burst_timeout_ms=3000,
            high_score_min_duration_ms=10000,
            min_key_count=5,
            min_duration_ms=500,  # Lower threshold for test (500ms)
        )

        detector = BurstDetector(
            config=config,
            on_burst_complete=lambda b: burst_completed.append(b),
        )

        # Simulate pressing only backspace (spaced out to meet duration)
        for i in range(5):
            # Space them 200ms apart, total duration = 800ms
            detector.process_key_event(1000 + (i * 200), True, is_backspace=True, key_name="BACKSPACE")

        # Complete the burst
        result = detector.process_key_event(15000, True, False, "a")

        assert result is not None
        assert result.backspace_count == 5
        assert result.key_count == 5
        assert result.backspace_ratio == 1.0


class TestBurstWordValidation:
    """Test word validation functionality in BurstDetector."""

    def test_gibberish_burst_rejected(self):
        """Test that random gibberish is rejected."""
        from unittest.mock import Mock

        burst_completed = []

        # Create a mock dictionary that returns False for all words
        mock_dict = Mock()
        mock_dict.is_valid_word = lambda word, lang: False

        config = BurstDetectorConfig(
            burst_timeout_ms=3000,
            high_score_min_duration_ms=10000,
            min_key_count=5,
            min_duration_ms=500,
            validate_burst_words=True,
            burst_word_validation_threshold=0.5,
            burst_min_word_length=3,
        )

        detector = BurstDetector(
            config=config,
            on_burst_complete=lambda b: burst_completed.append(b),
            dictionary=mock_dict,
            language="en",
        )

        # Type gibberish that should be rejected
        # "sjladkjfkls asdkl jfsak jdfkasljdflasjd flj sa ldfjlaskj df"
        gibberish = "sjladkjfkls asdkl jfsak jdfkasljdflasjd flj sa ldfjlaskj df"
        for i, char in enumerate(gibberish):
            detector.process_key_event(1000 + (i * 100), True, False, char)

        # Trigger burst completion
        result = detector.process_key_event(20000, True, False, " ")

        # Burst should be rejected due to invalid words
        assert result is None
        assert len(burst_completed) == 0

    def test_valid_words_burst_accepted(self):
        """Test that valid English words are accepted."""
        from unittest.mock import Mock

        burst_completed = []

        # Create a mock dictionary that returns True for all words
        mock_dict = Mock()
        mock_dict.is_valid_word = lambda word, lang: True

        config = BurstDetectorConfig(
            burst_timeout_ms=3000,
            high_score_min_duration_ms=10000,
            min_key_count=5,
            min_duration_ms=500,
            validate_burst_words=True,
            burst_word_validation_threshold=0.5,
            burst_min_word_length=3,
        )

        detector = BurstDetector(
            config=config,
            on_burst_complete=lambda b: burst_completed.append(b),
            dictionary=mock_dict,
            language="en",
        )

        # Type valid English text
        text = "hello world this is a test"
        for i, char in enumerate(text):
            detector.process_key_event(1000 + (i * 100), True, False, char)

        # Trigger burst completion
        result = detector.process_key_event(20000, True, False, " ")

        # Burst should be accepted
        assert result is not None
        assert result.key_count > 0

    def test_partial_valid_words_accepted(self):
        """Test that burst with some valid words passes threshold."""
        from unittest.mock import Mock

        burst_completed = []
        valid_words = {"hello", "world", "test"}

        # Create a mock dictionary that returns True only for specific words
        mock_dict = Mock()
        mock_dict.is_valid_word = lambda word, lang: word.lower() in valid_words

        config = BurstDetectorConfig(
            burst_timeout_ms=3000,
            high_score_min_duration_ms=10000,
            min_key_count=5,
            min_duration_ms=500,
            validate_burst_words=True,
            burst_word_validation_threshold=0.5,  # 50% threshold
            burst_min_word_length=3,
        )

        detector = BurstDetector(
            config=config,
            on_burst_complete=lambda b: burst_completed.append(b),
            dictionary=mock_dict,
            language="en",
        )

        # Type text with 60% valid words: "hello world xyz test abc"
        # Valid: hello, world, test (3 out of 5 = 60%)
        # Invalid: xyz, abc (2 out of 5 = 40%)
        text = "hello world xyz test abc"
        for i, char in enumerate(text):
            detector.process_key_event(1000 + (i * 100), True, False, char)

        # Trigger burst completion
        result = detector.process_key_event(20000, True, False, " ")

        # Burst should be accepted (60% > 50% threshold)
        assert result is not None

    def test_validation_disabled_always_accepts(self):
        """Test that validation can be disabled."""
        from unittest.mock import Mock

        burst_completed = []

        # Create a mock dictionary that returns False for all words
        mock_dict = Mock()
        mock_dict.is_valid_word = lambda word, lang: False

        config = BurstDetectorConfig(
            burst_timeout_ms=3000,
            high_score_min_duration_ms=10000,
            min_key_count=5,
            min_duration_ms=500,
            validate_burst_words=False,  # Disabled
            burst_word_validation_threshold=0.5,
            burst_min_word_length=3,
        )

        detector = BurstDetector(
            config=config,
            on_burst_complete=lambda b: burst_completed.append(b),
            dictionary=mock_dict,
            language="en",
        )

        # Type gibberish
        text = "sjladkjfkls asdkl jfsak"
        for i, char in enumerate(text):
            detector.process_key_event(1000 + (i * 100), True, False, char)

        # Trigger burst completion
        result = detector.process_key_event(20000, True, False, " ")

        # Burst should be accepted because validation is disabled
        assert result is not None

    def test_text_content_tracking(self):
        """Test that text content is tracked correctly."""
        config = BurstDetectorConfig(
            burst_timeout_ms=3000,
            high_score_min_duration_ms=10000,
            min_key_count=2,
            min_duration_ms=100,
            validate_burst_words=False,
        )

        detector = BurstDetector(config=config)

        # Type some text
        text = "hello world"
        for char in text:
            detector.process_key_event(1000, True, False, char)
            # Need to increment timestamp to avoid all being same timestamp
            # But for this test, we just want to check text tracking

        # Get current burst info
        current_burst = detector.current_burst
        assert current_burst is not None
        assert current_burst.text_content == text
