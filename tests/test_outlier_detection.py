"""Tests for burst outlier detection helpers."""

from core.outlier_detection import calculate_quartiles, detect_outlier_indices


def test_calculate_quartiles_even_sample():
    """Quartile calculation should return stable Tukey-style halves."""
    q1, q3, iqr = calculate_quartiles([10, 12, 14, 16, 18, 20, 22, 24])

    assert q1 == 13
    assert q3 == 21
    assert iqr == 8


def test_detect_high_outlier_with_clear_gap():
    """A clearly separated fast burst should be flagged as a high outlier."""
    values = [48, 49, 50, 50, 51, 51, 52, 52, 90]

    high, low, stats = detect_outlier_indices(values)

    assert high == [8]
    assert low == []
    assert stats["upper_fence"] < 90


def test_detect_low_outlier_with_clear_gap():
    """A clearly separated slow burst should be flagged as a low outlier."""
    values = [8, 48, 49, 50, 50, 51, 52, 52, 53]

    high, low, stats = detect_outlier_indices(values)

    assert high == []
    assert low == [0]
    assert stats["lower_fence"] > 8


def test_gap_filter_ignores_dense_upper_tail():
    """Small tails should not be marked as outliers without a meaningful gap."""
    values = [48, 49, 50, 50, 51, 52, 53, 54, 55]

    high, low, _ = detect_outlier_indices(values)

    assert high == []
    assert low == []
