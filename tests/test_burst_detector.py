"""Tests for BurstDetector class."""

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
            qualifies_for_high_score=True
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
            qualifies_for_high_score=False
        )

        # Duration should be 5000ms = 5 seconds
        assert burst.duration_ms == 5000


class TestBurstDetector:
    """Test BurstDetector class."""

    def test_init(self):
        """Test burst detector initialization."""
        burst_completed = []

        detector = BurstDetector(
            burst_timeout_ms=3000,
            high_score_min_duration_ms=10000,
            on_burst_complete=lambda b: burst_completed.append(b)
        )

        assert detector.config.burst_timeout_ms == 3000
        assert detector.config.high_score_min_duration_ms == 10000

    def test_single_keypress(self):
        """Test processing a single key press."""
        burst_completed = []

        detector = BurstDetector(
            burst_timeout_ms=3000,
            high_score_min_duration_ms=10000,
            on_burst_complete=lambda b: burst_completed.append(b)
        )

        # Process press and release
        detector.process_key_event(1000, True)  # press
        result = detector.process_key_event(1500, False)  # release

        # Should not complete a burst yet (waiting for timeout)
        assert result is None

    def test_burst_completion(self):
        """Test that burst completes after timeout."""
        burst_completed = []

        detector = BurstDetector(
            burst_timeout_ms=3000,
            high_score_min_duration_ms=10000,
            min_key_count=2,  # Lower threshold for test
            min_duration_ms=1000,  # Lower threshold for test
            on_burst_complete=lambda b: burst_completed.append(b)
        )

        # Process some key events
        detector.process_key_event(1000, True)
        detector.process_key_event(1200, False)
        detector.process_key_event(2000, True)
        detector.process_key_event(2200, False)

        # Trigger timeout
        result = detector.process_key_event(10000, True)  # Way past timeout

        assert result is not None
        assert isinstance(result, Burst)
        assert result.key_count == 2  # 2 complete key presses

    def test_high_score_qualification(self):
        """Test high score qualification."""
        burst_completed = []

        detector = BurstDetector(
            burst_timeout_ms=3000,
            high_score_min_duration_ms=10000,  # 10 seconds minimum
            min_key_count=2,  # Lower threshold for test
            min_duration_ms=1000,  # Lower threshold for test
            on_burst_complete=lambda b: burst_completed.append(b)
        )

        # Simulate a burst with less than 10 seconds duration but >1 second
        # Need 2 key presses to meet min_key_count
        detector.process_key_event(1000, True)   # First key press
        detector.process_key_event(2100, True)   # Second key press (1100ms later)

        # Complete the burst (timeout triggered)
        result = detector.process_key_event(10000, True)

        assert result is not None
        assert not result.qualifies_for_high_score  # Too short (duration < 10000ms)

    def test_high_score_qualified(self):
        """Test that longer bursts qualify for high score."""
        burst_completed = []

        detector = BurstDetector(
            burst_timeout_ms=3000,
            high_score_min_duration_ms=10000,  # 10 seconds minimum
            min_key_count=5,  # Lower threshold for test
            min_duration_ms=1000,  # Lower threshold for test
            on_burst_complete=lambda b: burst_completed.append(b)
        )

        # Simulate a 12-second burst (just key press/release events spread out)
        start_time = 1000
        for i in range(10):
            press_time = start_time + (i * 1200)
            release_time = press_time + 100
            detector.process_key_event(press_time, True)
            detector.process_key_event(release_time, False)

        # Complete the burst (timeout triggered)
        result = detector.process_key_event(start_time + 15000, True)

        assert result is not None
        # Should qualify because duration > 10 seconds
        # (start_time to last event is > 10 seconds)
        assert result.qualifies_for_high_score
