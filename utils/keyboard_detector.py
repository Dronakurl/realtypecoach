"""Keyboard layout detection for RealTypeCoach."""

import subprocess
import time
import threading
from typing import Callable, Optional


def get_current_layout() -> str:
    """Detect current keyboard layout using setxkbmap."""
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
                return layout.lower()
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        pass
    return 'us'


def get_available_layouts() -> list[str]:
    """Get list of available keyboard layouts."""
    try:
        result = subprocess.run(
            ['setxkbmap', '-query'],
            capture_output=True,
            text=True,
            timeout=5
        )
        layouts = []
        for line in result.stdout.split('\n'):
            if line.startswith('layout:'):
                layout = line.split(':')[1].strip()
                layouts.append(layout.lower())
        return list(set(layouts))
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
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
            self.thread.join(timeout=5)
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
