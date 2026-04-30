"""Outlier detection helpers for frontend burst visualizations."""

from statistics import median


def calculate_quartiles(values: list[float]) -> tuple[float, float, float]:
    """Calculate quartile statistics for a numeric sample."""
    if not values:
        return 0.0, 0.0, 0.0

    sorted_values = sorted(values)
    n = len(sorted_values)
    mid = n // 2

    lower_half = sorted_values[:mid]
    upper_half = sorted_values[mid:] if n % 2 == 0 else sorted_values[mid + 1 :]

    q1 = float(median(lower_half)) if lower_half else float(sorted_values[0])
    q3 = float(median(upper_half)) if upper_half else float(sorted_values[-1])
    return q1, q3, q3 - q1


def detect_outlier_indices(
    values: list[float],
    fence_multiplier: float = 1.5,
    gap_multiplier: float = 1.0,
    min_samples: int = 8,
) -> tuple[list[int], list[int], dict[str, float]]:
    """Detect high and low outliers using Tukey fences plus gap filtering.

    The extra gap filter prevents the far tail of a dense cluster from being
    treated as an outlier unless it is meaningfully separated from the closest
    non-outlier values.
    """
    if len(values) < min_samples:
        return [], [], {
            "median": float(median(values)) if values else 0.0,
            "q1": 0.0,
            "q3": 0.0,
            "iqr": 0.0,
            "upper_fence": 0.0,
            "lower_fence": 0.0,
        }

    q1, q3, iqr = calculate_quartiles(values)
    if iqr <= 0:
        median_value = float(median(values))
        return [], [], {
            "median": median_value,
            "q1": q1,
            "q3": q3,
            "iqr": iqr,
            "upper_fence": q3,
            "lower_fence": q1,
        }

    upper_fence = q3 + fence_multiplier * iqr
    lower_fence = q1 - fence_multiplier * iqr

    high_candidates = [i for i, value in enumerate(values) if value > upper_fence]
    low_candidates = [i for i, value in enumerate(values) if value < lower_fence]

    min_gap = gap_multiplier * iqr

    high_outliers = _filter_high_outliers(values, high_candidates, min_gap)
    low_outliers = _filter_low_outliers(values, low_candidates, min_gap)

    return high_outliers, low_outliers, {
        "median": float(median(values)),
        "q1": q1,
        "q3": q3,
        "iqr": iqr,
        "upper_fence": upper_fence,
        "lower_fence": lower_fence,
    }


def _filter_high_outliers(
    values: list[float], candidate_indices: list[int], min_gap: float
) -> list[int]:
    """Keep only high outliers that are well separated from the main cluster."""
    if not candidate_indices:
        return []

    non_candidates = [value for i, value in enumerate(values) if i not in candidate_indices]
    if not non_candidates:
        return []

    boundary = max(non_candidates)
    return [i for i in candidate_indices if values[i] - boundary >= min_gap]


def _filter_low_outliers(
    values: list[float], candidate_indices: list[int], min_gap: float
) -> list[int]:
    """Keep only low outliers that are well separated from the main cluster."""
    if not candidate_indices:
        return []

    non_candidates = [value for i, value in enumerate(values) if i not in candidate_indices]
    if not non_candidates:
        return []

    boundary = min(non_candidates)
    return [i for i in candidate_indices if boundary - values[i] >= min_gap]
