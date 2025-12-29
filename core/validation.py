"""Validation helpers for RealTypeCoach."""

import logging

log = logging.getLogger("realtypecoach.validation")


def validate_duration_ms(start_ms: int, end_ms: int) -> int:
    """Calculate duration, ensuring non-negative result.

    Args:
        start_ms: Start timestamp in milliseconds
        end_ms: End timestamp in milliseconds

    Returns:
        Duration in milliseconds (non-negative)
    """
    if start_ms < 0 or end_ms < 0:
        log.warning(f"Negative timestamp: start={start_ms}, end={end_ms}")
        return 0

    duration = end_ms - start_ms
    if duration < 0:
        log.warning(f"Negative duration: {duration}ms (start={start_ms}, end={end_ms})")
        return 0

    return duration
