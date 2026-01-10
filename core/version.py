"""Version information for RealTypeCoach."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Default fallback version (updated by post-commit hook)
DEFAULT_VERSION = "unknown"
VERSION_FILE = Path(__file__).parent / "VERSION"

# Cached version (module-level, computed once on import)
_cached_version: Optional[str] = None


def get_version() -> str:
    """Get version string from git commit timestamp.

    Returns version in format: "January 09, 2026 at 21:07"

    Priority:
    1. Read from VERSION file if exists (fast, reliable)
    2. Query git if available (fallback for development)
    3. Return "unknown" if neither available

    Returns:
        Version string
    """
    global _cached_version

    if _cached_version is not None:
        return _cached_version

    # Try reading from VERSION file first (fastest)
    if VERSION_FILE.exists():
        try:
            timestamp_str = VERSION_FILE.read_text().strip()
            # Convert Unix timestamp to formatted date
            ts = int(timestamp_str)
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            _cached_version = dt.strftime("%B %d, %Y at %H:%M")
            return _cached_version
        except (ValueError, OSError):
            pass  # Fall through to git query

    # Fallback: query git directly (for development without VERSION file)
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ct"],
            capture_output=True,
            text=True,
            timeout=1,  # Don't hang on git errors
            check=True,
            cwd=Path(__file__).parent.parent,
        )
        timestamp_str = result.stdout.strip()
        if timestamp_str:
            ts = int(timestamp_str)
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            _cached_version = dt.strftime("%B %d, %Y at %H:%M")
            return _cached_version
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError, TimeoutError):
        pass

    # Final fallback
    _cached_version = DEFAULT_VERSION
    return _cached_version


def get_version_timestamp_ms() -> int:
    """Get version as Unix timestamp in milliseconds.

    Useful for programmatic comparisons.

    Returns:
        Unix timestamp in milliseconds, or 0 if unknown
    """
    if VERSION_FILE.exists():
        try:
            timestamp_str = VERSION_FILE.read_text().strip()
            return int(timestamp_str) * 1000  # Convert seconds to milliseconds
        except (ValueError, OSError):
            pass

    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ct"],
            capture_output=True,
            text=True,
            timeout=1,
            check=True,
            cwd=Path(__file__).parent.parent,
        )
        timestamp_str = result.stdout.strip()
        if timestamp_str:
            return int(timestamp_str) * 1000
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError, TimeoutError):
        pass

    return 0


# Module-level convenience (computed once on import)
__version__ = get_version()
