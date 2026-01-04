"""Keyboard layout detection for RealTypeCoach."""

import os
import subprocess
import threading
import logging
from typing import Callable, Optional

log = logging.getLogger("realtypecoach.layout_monitor")

# Constants
SUBPROCESS_TIMEOUT = 5  # seconds
KEYBOARD_FILE_PATH = "/etc/default/keyboard"
FALLBACK_LAYOUT = "us"


def _query_layout_sources() -> list[str]:
    """Query all layout sources and return list of available layouts.

    Tries sources in priority order:
    1. XKB_DEFAULT_LAYOUT environment variable (Wayland session)
    2. localectl status (system configuration)
    3. /etc/default/keyboard file (Debian-based systems)
    4. setxkbmap -query (X11/Xwayland fallback)

    Returns:
        List of layout codes (e.g., ['de', 'us']) or [FALLBACK_LAYOUT]
    """
    # Method 1: Check XKB_DEFAULT_LAYOUT (Wayland)
    xkb_layout = os.environ.get("XKB_DEFAULT_LAYOUT")
    if xkb_layout:
        return [layout.strip().lower() for layout in xkb_layout.split(",")]

    # Method 2: Check localectl status
    try:
        result = subprocess.run(
            ["localectl", "status"],
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT,
        )
        for line in result.stdout.split("\n"):
            if "X11 Layout" in line:
                layout = line.split(":", 1)[1].strip()
                if layout:
                    return [layout.strip().lower() for layout in layout.split(",")]
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError, IndexError):
        pass

    # Method 3: Read /etc/default/keyboard
    try:
        with open(KEYBOARD_FILE_PATH, "r") as f:
            for line in f:
                if line.startswith("XKBLAYOUT="):
                    # Handle both XKBLAYOUT="de" and XKBLAYOUT=de
                    layout = line.split("=")[1].strip().strip("\"'")
                    if layout:
                        return [layout.strip().lower() for layout in layout.split(",")]
    except (FileNotFoundError, IOError, IndexError):
        pass

    # Method 4: Use setxkbmap (X11/Xwayland fallback)
    try:
        result = subprocess.run(
            ["setxkbmap", "-query"],
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT,
        )
        for line in result.stdout.split("\n"):
            if line.startswith("layout:"):
                layout = line.split(":")[1].strip()
                if layout:
                    return [layout.lower()]
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError, IndexError):
        pass

    return [FALLBACK_LAYOUT]


def get_current_layout() -> str:
    """Detect current keyboard layout using multiple methods with Wayland support.

    Detection priority:
    1. XKB_DEFAULT_LAYOUT environment variable (Wayland session)
    2. localectl status (system configuration)
    3. /etc/default/keyboard (Debian-based systems)
    4. setxkbmap -query (X11/Xwayland fallback)

    Returns:
        First available layout code (e.g., 'de') or FALLBACK_LAYOUT
    """
    return _query_layout_sources()[0]


def get_available_layouts() -> list[str]:
    """Get list of available keyboard layouts.

    Checks for multiple layouts configured (e.g., "de,us").

    Returns:
        List of layout codes (e.g., ['de', 'us']) or [FALLBACK_LAYOUT]
    """
    return _query_layout_sources()


class LayoutMonitor:
    """Monitor keyboard layout changes."""

    def __init__(self, callback: Callable[[str], None], poll_interval: int = 300):
        """Initialize layout monitor.

        Args:
            callback: Function to call when layout changes (receives new_layout)
            poll_interval: Seconds between checks (default 300)

        Raises:
            ValueError: If poll_interval is not positive
        """
        if poll_interval <= 0:
            raise ValueError("poll_interval must be positive")
        self.callback = callback
        self.poll_interval = poll_interval
        self.current_layout = get_current_layout()
        self.running = False
        self._stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start monitoring in background thread."""
        if self.running:
            return

        self.running = True
        self._stop_event.clear()
        self.thread = threading.Thread(target=self._monitor, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        """Stop monitoring."""
        self.running = False
        self._stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)
            self.thread = None

    def _monitor(self) -> None:
        """Background monitoring loop."""
        while not self._stop_event.is_set():
            new_layout = get_current_layout()
            with self._lock:
                if new_layout != self.current_layout:
                    self.current_layout = new_layout
                    try:
                        self.callback(new_layout)
                    except Exception as e:
                        log.error(f"Error in layout callback: {e}")
            self._stop_event.wait(self.poll_interval)
