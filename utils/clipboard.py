"""Clipboard utilities for Wayland and X11."""

import logging
import os
import subprocess

log = logging.getLogger("realtypecoach.clipboard")


def get_clipboard_content_wayland() -> str | None:
    """Get clipboard content on Wayland using wl-paste.

    Returns:
        Clipboard content as string, or None if empty/failed
    """
    try:
        result = subprocess.run(
            ["wl-paste", "--no-newline"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False
        )

        if result.returncode == 0 and result.stdout.strip():
            content = result.stdout.strip()
            log.debug(f"Got clipboard content via wl-paste: {len(content)} chars")
            return content
        return None

    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        log.warning(f"wl-paste failed: {e}")
        return None


def is_wayland() -> bool:
    """Detect if running on Wayland."""
    return os.environ.get("WAYLAND_DISPLAY") is not None or \
           os.environ.get("XDG_SESSION_TYPE") == "wayland"
