"""Shared utilities for frequency-based filtering."""

from typing import TypeVar, Callable
import logging

log = logging.getLogger("realtypecoach.frequency_utils")

T = TypeVar('T')


def filter_by_frequency_threshold(
    items: list[T],
    frequency_getter: Callable[[T], float],
    threshold: float
) -> list[T]:
    """Filter items by minimum frequency threshold.

    Args:
        items: List of items to filter
        frequency_getter: Function that extracts frequency from each item
        threshold: Minimum frequency value (inclusive)

    Returns:
        Filtered list with items >= threshold
    """
    return [item for item in items if frequency_getter(item) >= threshold]


def get_zipf_threshold_name(zipf: float) -> str:
    """Get human-readable name for Zipf threshold.

    Args:
        zipf: Zipf frequency value

    Returns:
        Descriptive name (e.g., "Very Common", "Moderate", "Rare")
    """
    if zipf >= 6.0:
        return "Very Common"
    elif zipf >= 5.0:
        return "Common"
    elif zipf >= 4.0:
        return "Moderate"
    elif zipf >= 3.0:
        return "Uncommon"
    else:
        return "Rare"


def get_primary_language(config) -> str:
    """Get primary language from config.

    Returns first enabled language, or 'en' as fallback.

    Args:
        config: Config object

    Returns:
        Primary language code (e.g., 'en', 'de')
    """
    enabled = config.get("enabled_languages", "en")
    if isinstance(enabled, str):
        languages = enabled.split(",")
    else:
        languages = enabled
    return languages[0].strip() if languages else "en"
