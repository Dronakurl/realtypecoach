"""Tests for Analyzer class."""

import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from core.analyzer import Analyzer
from core.burst_detector import Burst
from core.storage import Storage
from utils.config import Config
from utils.crypto import CryptoManager


def get_today_timestamp_ms(offset_seconds=0):
    """Get timestamp in milliseconds for today."""
    return int((datetime.now().timestamp() + offset_seconds) * 1000)


@pytest.fixture
def temp_db():
    """Create temporary database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    db_path.unlink()


@pytest.fixture
def storage(temp_db):
    """Create storage with temporary database."""
    # Initialize encryption key first
    crypto = CryptoManager(temp_db)
    if not crypto.key_exists():
        crypto.initialize_database_key()

    config = Config(temp_db)
    return Storage(temp_db, config=config)


@pytest.fixture
def analyzer(storage):
    """Create analyzer with temporary storage."""
    return Analyzer(storage)


class TestAnalyzer:
    """Test Analyzer class."""

    def test_init(self, analyzer):
        """Test analyzer initialization."""
        assert analyzer.storage is not None
        assert not analyzer.running
        assert analyzer.today_stats["total_keystrokes"] == 0
        assert analyzer.today_stats["total_typing_ms"] == 0

    def test_process_key_event(self, analyzer):
        """Test processing key events."""
        timestamp_ms = 1234567890
        analyzer.process_key_event(30, "KEY_A", timestamp_ms, "us")

        # Should increment keystrokes
        assert analyzer.today_stats["total_keystrokes"] == 1

    def test_process_burst(self, analyzer):
        """Test processing bursts."""
        start = get_today_timestamp_ms()
        burst = Burst(
            start_time_ms=start,
            end_time_ms=start + 5000,
            key_count=50,
            duration_ms=5000,
            qualifies_for_high_score=True,
        )

        analyzer.process_burst(burst)

        # Should update statistics
        assert analyzer.today_stats["total_bursts"] == 1
        assert analyzer.today_stats["total_typing_ms"] == 5000

    def test_typing_time_units(self, analyzer):
        """Test that typing time units are consistent."""
        # Process a burst with 5 second duration
        start = get_today_timestamp_ms()
        burst = Burst(
            start_time_ms=start,
            end_time_ms=start + 5000,
            key_count=50,
            duration_ms=5000,  # 5 seconds in milliseconds
            qualifies_for_high_score=False,
        )

        analyzer.process_burst(burst)

        stats = analyzer.get_statistics()

        # total_typing_sec should be in seconds, not milliseconds
        # Now calculated from database, so should be 5.0 seconds
        assert stats["total_typing_sec"] == 5.0  # 5 seconds, not 5000

    def test_multiple_bursts_typing_time(self, analyzer):
        """Test typing time accumulation across multiple bursts."""
        # Process multiple bursts
        base = get_today_timestamp_ms()
        bursts = [
            Burst(
                start_time_ms=base,
                end_time_ms=base + 5000,
                key_count=10,
                backspace_count=0,
                net_key_count=10,
                duration_ms=5000,
                qualifies_for_high_score=False,
            ),
            Burst(
                start_time_ms=base + 6000,
                end_time_ms=base + 11000,
                key_count=15,
                backspace_count=0,
                net_key_count=15,
                duration_ms=5000,
                qualifies_for_high_score=False,
            ),
            Burst(
                start_time_ms=base + 12000,
                end_time_ms=base + 17000,
                key_count=20,
                backspace_count=0,
                net_key_count=20,
                duration_ms=5000,
                qualifies_for_high_score=False,
            ),
        ]

        for burst in bursts:
            analyzer.process_burst(burst)

        stats = analyzer.get_statistics()

        # 3 bursts × 5 seconds each = 15 seconds total
        assert stats["total_typing_sec"] == 15.0
        assert stats["total_bursts"] == 3

    def test_calculate_wpm(self, analyzer):
        """Test WPM calculation."""
        # 100 keystrokes in 30 seconds
        # words = 100 / 5 = 20 words
        # minutes = 30 / 60 = 0.5 minutes
        # WPM = 20 / 0.5 = 40 WPM
        wpm = analyzer._calculate_wpm(100, 30000)
        assert abs(wpm - 40.0) < 0.1

    def test_calculate_wpm_with_backspaces(self, analyzer):
        """Test WPM calculation subtracts 2 for each backspace."""
        # 100 keystrokes in 30 seconds, but 20 were backspaces
        # Each backspace removes 1 character + itself = 2 net reduction
        # Net: 100 - (20*2) = 60 keystrokes = 12 words / 0.5 min = 24 WPM
        wpm = analyzer._calculate_wpm(100, 30000, 20)
        assert abs(wpm - 24.0) < 0.1

    def test_calculate_wpm_all_backspaces(self, analyzer):
        """Test WPM calculation when all keystrokes are backspaces."""
        # 100 keystrokes but all 100 are backspaces
        # Net: 0 keystrokes = 0 WPM
        wpm = analyzer._calculate_wpm(100, 30000, 100)
        assert wpm == 0.0

    def test_process_burst_with_backspaces(self, analyzer):
        """Test burst processing with backspaces tracked."""
        base = get_today_timestamp_ms()
        burst = Burst(
            start_time_ms=base,
            end_time_ms=base + 30000,  # 30 seconds
            key_count=100,  # Total keystrokes
            backspace_count=20,  # 20 backspaces
            net_key_count=60,  # 100 - (20*2) = 60 productive keystrokes
            duration_ms=30000,
            qualifies_for_high_score=True,
        )

        analyzer.process_burst(burst)

        # WPM should be calculated from net keystrokes
        # 60 net keystrokes = 12 words / 0.5 min = 24 WPM
        assert abs(analyzer.current_burst_wpm - 24.0) < 0.1

        # Verify storage received correct data
        with analyzer.storage._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key_count, backspace_count, net_key_count, avg_wpm FROM bursts")
            result = cursor.fetchone()

            assert result[0] == 100  # key_count
            assert result[1] == 20  # backspace_count
            assert result[2] == 60  # net_key_count (100 - 20*2)
            assert abs(result[3] - 24.0) < 0.1  # avg_wpm calculated from net

    def test_get_statistics_returns_correct_types(self, analyzer):
        """Test that get_statistics returns correct types."""
        stats = analyzer.get_statistics()

        assert isinstance(stats["total_keystrokes"], int)
        assert isinstance(stats["total_bursts"], int)
        assert isinstance(stats["total_typing_sec"], float)
        assert isinstance(stats["avg_wpm"], float)

    def test_daily_summary_storage(self, analyzer):
        """Test that daily summary stores typing time correctly."""
        # Create some typing activity (need key events to have keystrokes count)
        base = get_today_timestamp_ms()
        for i in range(50):
            analyzer.process_key_event(30, "KEY_A", base + (i * 100), "us")

        burst = Burst(
            start_time_ms=base,
            end_time_ms=base + 10000,
            key_count=50,
            backspace_count=0,
            net_key_count=50,
            duration_ms=10000,  # 10 seconds
            qualifies_for_high_score=False,
        )
        analyzer.process_burst(burst)

        # Finalize the day by calling _new_day with a new date
        # This will finalize the current day and start a new one
        old_date = analyzer.today_date
        new_date = "2099-01-01"  # Far future date
        analyzer._new_day(new_date)

        # Check the daily summary for the old day
        summary = analyzer.storage.get_daily_summary(old_date)

        assert summary is not None
        # total_typing_sec should be in seconds
        assert summary.total_typing_sec == 10  # 10 seconds, not 10000

    def test_wpm_burst_sequence_no_smoothing(self, analyzer):
        """Test that smoothness=1 returns raw data with same number of points."""
        # Create test data with varying WPM values
        base = get_today_timestamp_ms()
        wpm_values = [40.0, 60.0, 35.0, 70.0, 45.0, 80.0, 50.0, 65.0, 30.0, 75.0]

        for i, wpm in enumerate(wpm_values):
            # Create bursts that result in the desired WPM
            burst = Burst(
                start_time_ms=base + (i * 6000),
                end_time_ms=base + (i * 6000) + 5000,
                key_count=int(wpm * 5 / 12),  # Approximate to get target WPM
                backspace_count=0,
                net_key_count=int(wpm * 5 / 12),
                duration_ms=5000,
                qualifies_for_high_score=False,
            )
            analyzer.process_burst(burst)

        # Get raw data (smoothness=1)
        result_wpm, result_x = analyzer.get_wpm_burst_sequence(smoothness=1)

        # Should have same number of points as input
        assert len(result_wpm) == len(wpm_values)
        # X positions should be 1-indexed burst numbers
        assert result_x == list(range(1, 11))
        # Verify values match closely (actual WPM calculation may vary slightly)
        for actual, expected in zip(result_wpm, wpm_values, strict=False):
            assert abs(actual - expected) < 5.0  # Allow 5 WPM tolerance

    def test_wpm_burst_sequence_moving_average(self, analyzer):
        """Test that moving average smooths while keeping all points."""
        # Create test data with 100 bursts
        base = get_today_timestamp_ms()
        wpm_values = []
        for i in range(100):
            wpm = 40.0 + (i % 10) * 5.0  # Varying WPM between 40-85
            wpm_values.append(wpm)
            burst = Burst(
                start_time_ms=base + (i * 6000),
                end_time_ms=base + (i * 6000) + 5000,
                key_count=int(wpm * 5 / 12),
                backspace_count=0,
                net_key_count=int(wpm * 5 / 12),
                duration_ms=5000,
                qualifies_for_high_score=False,
            )
            analyzer.process_burst(burst)

        # Get smoothed data with maximum smoothness
        result_wpm, result_x = analyzer.get_wpm_burst_sequence(smoothness=100)

        # Should keep all 100 points
        assert len(result_wpm) == 100
        # X positions should be 1-100
        assert result_x == list(range(1, 101))
        # Calculate variance - smoothed should have less variance
        raw_variance = np.var(wpm_values)
        smoothed_variance = np.var(result_wpm)
        assert smoothed_variance < raw_variance
