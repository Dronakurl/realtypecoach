"""Tests for WPM calculator utilities."""

import pytest

from core.wpm_calculator import calculate_wpm, calculate_net_keystrokes


class TestCalculateWPM:
    """Test calculate_wpm function."""

    def test_basic_wpm_calculation(self):
        """Test basic WPM calculation.

        100 keystrokes in 30 seconds:
        - words = 100 / 5 = 20 words
        - minutes = 30 / 60 = 0.5 minutes
        - WPM = 20 / 0.5 = 40 WPM
        """
        wpm = calculate_wpm(100, 30000)
        assert abs(wpm - 40.0) < 0.1

    def test_zero_duration(self):
        """Test WPM calculation with zero duration returns 0."""
        wpm = calculate_wpm(100, 0)
        assert wpm == 0.0

    def test_zero_keystrokes(self):
        """Test WPM calculation with zero keystrokes returns 0."""
        wpm = calculate_wpm(0, 30000)
        assert wpm == 0.0

    def test_one_minute_exact(self):
        """Test WPM calculation for exactly one minute.

        250 keystrokes (50 words) in 60 seconds = 50 WPM.
        """
        wpm = calculate_wpm(250, 60000)
        assert abs(wpm - 50.0) < 0.1

    def test_high_wpm(self):
        """Test WPM calculation for high typing speed.

        500 keystrokes (100 words) in 30 seconds = 200 WPM.
        """
        wpm = calculate_wpm(500, 30000)
        assert abs(wpm - 200.0) < 0.1

    def test_low_wpm(self):
        """Test WPM calculation for low typing speed.

        25 keystrokes (5 words) in 60 seconds = 5 WPM.
        """
        wpm = calculate_wpm(25, 60000)
        assert abs(wpm - 5.0) < 0.1


class TestCalculateNetKeystrokes:
    """Test calculate_net_keystrokes function."""

    def test_no_backspaces(self):
        """Test net keystrokes with no backspaces."""
        net = calculate_net_keystrokes(100, 0)
        assert net == 100

    def test_with_backspaces(self):
        """Test net keystrokes subtracts 2 for each backspace.

        100 keystrokes, 20 backspaces:
        - Each backspace removes 1 character + itself = 2
        - Net: 100 - (20 * 2) = 60
        """
        net = calculate_net_keystrokes(100, 20)
        assert net == 60

    def test_all_backspaces(self):
        """Test net keystrokes when all are backspaces.

        100 keystrokes, 100 backspaces:
        - Net: 100 - (100 * 2) = -100, but max(0, ...) = 0
        """
        net = calculate_net_keystrokes(100, 100)
        assert net == 0

    def test_more_backspaces_than_keystrokes(self):
        """Test net keystrokes when backspaces exceed keystrokes."""
        net = calculate_net_keystrokes(50, 100)
        assert net == 0  # Should never be negative

    def test_half_backspaces(self):
        """Test net keystrokes with half being backspaces.

        100 keystrokes, 50 backspaces:
        - Net: 100 - (50 * 2) = 0
        """
        net = calculate_net_keystrokes(100, 50)
        assert net == 0

    def test_single_backspace(self):
        """Test net keystrokes with one backspace.

        10 keystrokes, 1 backspace:
        - Net: 10 - (1 * 2) = 8
        """
        net = calculate_net_keystrokes(10, 1)
        assert net == 8
