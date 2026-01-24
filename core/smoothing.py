"""Smoothing algorithms for time series data."""


def apply_moving_average(wpm_values: list[float], smoothness: int) -> tuple[list[float], list[int]]:
    """Apply centered moving average smoothing to time series.

    Uses a centered moving average that keeps all data points while
    smoothing the curve. The window size is adaptive to data length.

    Args:
        wpm_values: List of WPM values per burst
        smoothness: Smoothing level (1-100)
                     1 = raw data (window_size=1)
                     100 = maximum smoothing (window_size ~5% of data)

    Returns:
        Tuple of (smoothed_wpm_values, x_positions)
        - x_positions are the burst numbers for each point (1-indexed)
    """
    if not wpm_values or smoothness <= 1:
        return wpm_values[:], list(range(1, len(wpm_values) + 1))

    n = len(wpm_values)

    # Adaptive window size: max 20% of data length, minimum 5
    # smoothness 1 -> window_size=1 (no smoothing)
    # smoothness 100 -> window_size=max(5, n * 0.20)
    max_window = max(5, int(n * 0.20))
    window_size = 1 + int((smoothness - 1) / 99 * (max_window - 1))

    # Ensure window_size is odd for centered moving average
    if window_size % 2 == 0:
        window_size += 1

    # Apply centered moving average
    half_window = window_size // 2
    result = []
    x_positions = []

    for i in range(n):
        # Calculate window bounds
        start = max(0, i - half_window)
        end = min(n, i + half_window + 1)

        # Get window and calculate mean
        window = wpm_values[start:end]
        result.append(sum(window) / len(window))
        x_positions.append(i + 1)  # 1-indexed burst number

    return result, x_positions
