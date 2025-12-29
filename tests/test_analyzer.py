"""Tests for Analyzer class."""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime
import sys
import time
sys.path.insert(0, '.')

from core.storage import Storage
from core.analyzer import Analyzer
from core.burst_detector import Burst


def get_today_timestamp_ms(offset_seconds=0):
    """Get timestamp in milliseconds for today."""
    return int((datetime.now().timestamp() + offset_seconds) * 1000)


@pytest.fixture
def temp_db():
    """Create temporary database."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    db_path.unlink()


@pytest.fixture
def storage(temp_db):
    """Create storage with temporary database."""
    return Storage(temp_db)


@pytest.fixture
def analyzer(storage):
    """Create analyzer with temporary storage."""
    return Analyzer(storage)


class TestAnalyzer:
    """Test Analyzer class."""

    def test_init(self, analyzer):
        """Test analyzer initialization."""
        assert analyzer.storage is not None
        assert analyzer.running == False
        assert analyzer.today_stats['total_keystrokes'] == 0
        assert analyzer.today_stats['total_typing_ms'] == 0

    def test_process_key_event(self, analyzer):
        """Test processing key events."""
        timestamp_ms = 1234567890
        analyzer.process_key_event(30, 'KEY_A', timestamp_ms, 'press', 'test_app', 'us')

        # Should increment keystrokes
        assert analyzer.today_stats['total_keystrokes'] == 1

    def test_process_burst(self, analyzer):
        """Test processing bursts."""
        start = get_today_timestamp_ms()
        burst = Burst(
            start_time_ms=start,
            end_time_ms=start + 5000,
            key_count=50,
            duration_ms=5000,
            qualifies_for_high_score=True
        )

        analyzer.process_burst(burst)

        # Should update statistics
        assert analyzer.today_stats['total_bursts'] == 1
        assert analyzer.today_stats['total_typing_ms'] == 5000

    def test_typing_time_units(self, analyzer):
        """Test that typing time units are consistent."""
        # Process a burst with 5 second duration
        start = get_today_timestamp_ms()
        burst = Burst(
            start_time_ms=start,
            end_time_ms=start + 5000,
            key_count=50,
            duration_ms=5000,  # 5 seconds in milliseconds
            qualifies_for_high_score=False
        )

        analyzer.process_burst(burst)

        stats = analyzer.get_statistics()

        # total_typing_sec should be in seconds, not milliseconds
        # Now calculated from database, so should be 5.0 seconds
        assert stats['total_typing_sec'] == 5.0  # 5 seconds, not 5000

    def test_multiple_bursts_typing_time(self, analyzer):
        """Test typing time accumulation across multiple bursts."""
        # Process multiple bursts
        base = get_today_timestamp_ms()
        bursts = [
            Burst(start_time_ms=base, end_time_ms=base + 5000, key_count=10, duration_ms=5000, qualifies_for_high_score=False),
            Burst(start_time_ms=base + 6000, end_time_ms=base + 11000, key_count=15, duration_ms=5000, qualifies_for_high_score=False),
            Burst(start_time_ms=base + 12000, end_time_ms=base + 17000, key_count=20, duration_ms=5000, qualifies_for_high_score=False),
        ]

        for burst in bursts:
            analyzer.process_burst(burst)

        stats = analyzer.get_statistics()

        # 3 bursts × 5 seconds each = 15 seconds total
        assert stats['total_typing_sec'] == 15.0
        assert stats['total_bursts'] == 3

    def test_calculate_wpm(self, analyzer):
        """Test WPM calculation."""
        # 100 keystrokes in 30 seconds
        # words = 100 / 5 = 20 words
        # minutes = 30 / 60 = 0.5 minutes
        # WPM = 20 / 0.5 = 40 WPM
        wpm = analyzer._calculate_wpm(100, 30000)
        assert abs(wpm - 40.0) < 0.1

    def test_get_statistics_returns_correct_types(self, analyzer):
        """Test that get_statistics returns correct types."""
        stats = analyzer.get_statistics()

        assert isinstance(stats['total_keystrokes'], int)
        assert isinstance(stats['total_bursts'], int)
        assert isinstance(stats['total_typing_sec'], float)
        assert isinstance(stats['avg_wpm'], float)

    def test_daily_summary_storage(self, analyzer):
        """Test that daily summary stores typing time correctly."""
        # Create some typing activity (need key events to have keystrokes count)
        base = get_today_timestamp_ms()
        for i in range(50):
            analyzer.process_key_event(30, 'KEY_A', base + (i * 100), 'press', 'test_app', 'us')

        burst = Burst(
            start_time_ms=base,
            end_time_ms=base + 10000,
            key_count=50,
            duration_ms=10000,  # 10 seconds
            qualifies_for_high_score=False
        )
        analyzer.process_burst(burst)

        # Finalize the day
        analyzer._finalize_day()

        # Check the daily summary
        summary = analyzer.storage.get_daily_summary(analyzer.today_date)

        assert summary is not None
        keystrokes, bursts, avg_wpm, slowest_keycode, slowest_key_name, total_typing_sec, summary_sent = summary

        # total_typing_sec should be in seconds
        assert total_typing_sec == 10  # 10 seconds, not 10000
