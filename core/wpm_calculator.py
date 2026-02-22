"""WPM calculation utilities."""


def calculate_wpm(key_count: int, duration_ms: int) -> float:
    """Calculate words per minute.

    Args:
        key_count: Number of keystrokes (should be net, with backspaces already subtracted)
        duration_ms: Duration in milliseconds

    Returns:
        WPM (words per minute), or 0.0 if duration is zero
    """
    if duration_ms == 0:
        return 0.0

    words = key_count / 5.0
    minutes = duration_ms / 60000.0
    return words / minutes if minutes > 0 else 0.0


def calculate_net_keystrokes(key_count: int, backspace_count: int) -> int:
    """Calculate net keystrokes accounting for backspaces.

    Each backspace removes 1 character + the backspace itself = 2 net reduction.

    Args:
        key_count: Total keystrokes
        backspace_count: Number of backspace keystrokes

    Returns:
        Net keystrokes (never negative)
    """
    return max(0, key_count - (backspace_count * 2))
