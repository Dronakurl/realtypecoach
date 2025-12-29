"""Keyboard layout detection for RealTypeCoach."""

import os
import subprocess
import time
import threading
from typing import Callable, Optional


def get_current_layout() -> str:
    """Detect current keyboard layout using multiple methods with Wayland support.

    Detection priority:
    1. XKB_DEFAULT_LAYOUT environment variable (Wayland session)
    2. localectl status (system configuration)
    3. /etc/default/keyboard (Debian-based systems)
    4. setxkbmap -query (X11/Xwayland fallback)
    """
    # Method 1: Check XKB_DEFAULT_LAYOUT (Wayland)
    xkb_layout = os.environ.get('XKB_DEFAULT_LAYOUT')
    if xkb_layout:
        # Handle multiple layouts (e.g., "de,us")
        return xkb_layout.split(',')[0].strip().lower()

    # Method 2: Check localectl status
    try:
        result = subprocess.run(
            ['localectl', 'status'],
            capture_output=True,
            text=True,
            timeout=5
        )
        for line in result.stdout.split('\n'):
            if 'X11 Layout' in line:
                layout = line.split(':')[1].strip()
                if layout:
                    return layout.lower()
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError, IndexError):
        pass

    # Method 3: Read /etc/default/keyboard
    try:
        with open('/etc/default/keyboard', 'r') as f:
            for line in f:
                if line.startswith('XKBLAYOUT='):
                    # Handle both XKBLAYOUT="de" and XKBLAYOUT=de
                    layout = line.split('=')[1].strip().strip('"\'')
                    if layout:
                        return layout.split(',')[0].lower()
    except (FileNotFoundError, IOError, IndexError):
        pass

    # Method 4: Use setxkbmap (X11/Xwayland fallback)
    try:
        result = subprocess.run(
            ['setxkbmap', '-query'],
            capture_output=True,
            text=True,
            timeout=5
        )
        for line in result.stdout.split('\n'):
            if line.startswith('layout:'):
                layout = line.split(':')[1].strip()
                if layout:
                    return layout.lower()
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError, IndexError):
        pass

    return 'us'  # Ultimate fallback


def get_available_layouts() -> list[str]:
    """Get list of available keyboard layouts.

    Checks for multiple layouts configured (e.g., "de,us").
    """
    # Method 1: XKB_DEFAULT_LAYOUT
    xkb_layout = os.environ.get('XKB_DEFAULT_LAYOUT')
    if xkb_layout:
        return [l.strip().lower() for l in xkb_layout.split(',')]

    # Method 2: localectl status
    try:
        result = subprocess.run(
            ['localectl', 'status'],
            capture_output=True,
            text=True,
            timeout=5
        )
        for line in result.stdout.split('\n'):
            if 'X11 Layout' in line and line.count(':') >= 1:
                layout_part = line.split(':', 1)[1].strip()
                if layout_part:
                    return [l.strip().lower() for l in layout_part.split(',')]
    except Exception:
        pass

    # Method 3: /etc/default/keyboard
    try:
        with open('/etc/default/keyboard', 'r') as f:
            for line in f:
                if line.startswith('XKBLAYOUT='):
                    layout = line.split('=')[1].strip().strip('"\'')
                    if layout:
                        return [l.strip().lower() for l in layout.split(',')]
    except Exception:
        pass

    # Method 4: setxkbmap
    try:
        result = subprocess.run(
            ['setxkbmap', '-query'],
            capture_output=True,
            text=True,
            timeout=5
        )
        for line in result.stdout.split('\n'):
            if line.startswith('layout:'):
                layout = line.split(':')[1].strip()
                if layout:
                    return [layout.lower()]
    except Exception:
        pass

    return ['us']


class LayoutMonitor:
    """Monitor keyboard layout changes."""

    def __init__(self, callback: Callable[[str], None], poll_interval: int = 60):
        """Initialize layout monitor.

        Args:
            callback: Function to call when layout changes (receives new_layout)
            poll_interval: Seconds between checks (default 60)
        """
        self.callback = callback
        self.poll_interval = poll_interval
        self.current_layout = get_current_layout()
        self.running = False
        self.thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start monitoring in background thread."""
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._monitor, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        """Stop monitoring."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)
            self.thread = None

    def _monitor(self) -> None:
        """Background monitoring loop."""
        while self.running:
            new_layout = get_current_layout()
            if new_layout != self.current_layout:
                old_layout = self.current_layout
                self.current_layout = new_layout
                try:
                    self.callback(new_layout)
                except Exception as e:
                    print(f"Error in layout callback: {e}")
            time.sleep(self.poll_interval)
