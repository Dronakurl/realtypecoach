"""Hostname utilities for RealTypeCoach."""

import socket


def get_hostname() -> str:
    """Get current machine hostname.

    Returns cleaned hostname (lowercase, alphanumeric and underscores only,
    truncated to 20 characters max).

    Returns:
        Cleaned hostname string, or 'device' if hostname cannot be determined
    """
    try:
        hostname = socket.gethostname()
        # Clean up hostname: lowercase, alphanumeric and underscores only
        hostname = "".join(c.lower() if c.isalnum() else "_" for c in hostname)
        # Truncate to reasonable length
        return hostname[:20]
    except Exception:
        return "device"
