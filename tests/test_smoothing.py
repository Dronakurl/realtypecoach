"""Tests for smoothing algorithms."""

import pytest

from core.smoothing import apply_exponential_smoothing, smoothness_to_alpha


class TestSmoothnessToAlpha:
    """Test smoothness to alpha conversion (matches keybr.com)."""

    def test_smoothness_0_returns_alpha_1(self):
        """Smoothness of 0 should return alpha of 1.0 (no smoothing)."""
        assert smoothness_to_alpha(0) == 1.0

    def test_smoothness_negative_returns_alpha_1(self):
        """Smoothness of negative should return alpha of 1.0."""
        assert smoothness_to_alpha(-10) == 1.0

    def test_smoothness_100_returns_small_alpha(self):
        """Smoothness of 100 should return very small alpha (0.001)."""
        alpha = smoothness_to_alpha(100)
        assert alpha == pytest.approx(0.001, abs=0.0001)

    def test_smoothness_50_returns_moderate_alpha(self):
        """Smoothness of 50 should return moderate alpha (~0.0316)."""
        alpha = smoothness_to_alpha(50)
        # keybr.com: 1 / 10^(0.5 * 3) = 1 / 10^1.5 ≈ 0.0316
        assert 0.02 < alpha < 0.05

    def test_alpha_monotonically_decreases(self):
        """As smoothness increases, alpha should decrease."""
        alphas = [smoothness_to_alpha(s) for s in range(0, 101)]
        for i in range(1, len(alphas)):
            assert alphas[i] <= alphas[i - 1]


class TestExponentialSmoothing:
    """Test exponential smoothing function (matches keybr.com)."""

    def test_empty_list_returns_empty(self):
        """Empty input should return empty output."""
        result_wpm, result_x = apply_exponential_smoothing([], 50)
        assert result_wpm == []
        assert result_x == []

    def test_smoothness_0_returns_input(self):
        """Smoothness of 0 should return exact input."""
        input_wpm = [40.0, 60.0, 35.0, 70.0, 45.0]
        result_wpm, result_x = apply_exponential_smoothing(input_wpm, 0)

        assert result_wpm == input_wpm
        assert result_x == [1, 2, 3, 4, 5]

    def test_first_value_unchanged(self):
        """First value should always be unchanged."""
        input_wpm = [40.0, 60.0, 35.0, 70.0, 45.0]

        for smoothness in [0, 25, 50, 75, 100]:
            result_wpm, _ = apply_exponential_smoothing(input_wpm, smoothness)
            assert result_wpm[0] == input_wpm[0]

    def test_higher_smoothness_produces_smoother_output(self):
        """Higher smoothness should reduce variance for noisy data."""
        import numpy as np

        # Use noisy data
        import random
        random.seed(42)
        input_wpm = [50.0 + random.gauss(0, 10) for _ in range(100)]

        result_light, _ = apply_exponential_smoothing(input_wpm, 25)
        result_medium, _ = apply_exponential_smoothing(input_wpm, 50)
        result_heavy, _ = apply_exponential_smoothing(input_wpm, 100)

        var_light = np.var(result_light)
        var_medium = np.var(result_medium)
        var_heavy = np.var(result_heavy)

        # Higher smoothness should have lower variance
        assert var_heavy < var_medium < var_light

    def test_values_stay_within_range(self):
        """Smoothed values should stay within input range."""
        input_wpm = [40.0, 60.0, 35.0, 70.0, 45.0, 80.0, 50.0, 65.0, 30.0, 75.0]

        result_wpm, _ = apply_exponential_smoothing(input_wpm, 50)

        # Exponential smoothing stays within bounds
        assert min(result_wpm) >= min(input_wpm)
        assert max(result_wpm) <= max(input_wpm)

    def test_x_positions_correct(self):
        """X positions should be 1-indexed burst numbers."""
        input_wpm = [40.0, 60.0, 35.0]
        result_wpm, result_x = apply_exponential_smoothing(input_wpm, 50)

        assert result_x == [1, 2, 3]

    def test_preserves_point_count(self):
        """Should preserve the number of data points."""
        for length in [1, 5, 10, 50, 100]:
            input_wpm = [40.0] * length
            result_wpm, _ = apply_exponential_smoothing(input_wpm, 50)

            assert len(result_wpm) == length
