"""Smoothing algorithms for time series data.

Matches keybr.com exponential smoothing algorithm.
"""


def smoothness_to_alpha(smoothness: int) -> float:
    """Convert smoothness slider value (0-100) to exponential smoothing alpha.

    Matches keybr.com formula: alpha = 1 / 10^(smoothness * 3)
    where smoothness is normalized to 0-1 range.

    Mapping:
        0   -> alpha=1.0     (no smoothing, raw data)
        50  -> alpha≈0.0316  (moderate smoothing)
        100 -> alpha=0.001   (maximum smoothing)

    Args:
        smoothness: Smoothing level (0-100)

    Returns:
        Alpha value for exponential smoothing (0.001-1.0)
    """
    if smoothness <= 0:
        return 1.0
    normalized = smoothness / 100.0
    return 1.0 / (10.0 ** (normalized * 3))


def apply_exponential_smoothing(
    wpm_values: list[float],
    smoothness: int
) -> tuple[list[float], list[int]]:
    """Apply exponential smoothing to time series.

    Uses simple exponential smoothing: value_new = alpha * input_value + (1 - alpha) * value_previous
    Matches keybr.com algorithm for consistent behavior.

    Args:
        wpm_values: List of WPM values per burst
        smoothness: Smoothing level (0-100)
                     0 = raw data (alpha=1.0)
                     100 = maximum smoothing (alpha=0.001)

    Returns:
        Tuple of (smoothed_wpm_values, x_positions)
        - x_positions are the burst numbers for each point (1-indexed)
    """
    if not wpm_values or smoothness <= 0:
        return wpm_values[:], list(range(1, len(wpm_values) + 1))

    alpha = smoothness_to_alpha(smoothness)

    smoothed = []
    for i, value in enumerate(wpm_values):
        if i == 0:
            smoothed.append(value)
        else:
            smoothed.append(alpha * value + (1 - alpha) * smoothed[-1])

    return smoothed, list(range(1, len(wpm_values) + 1))
