"""AT-SPI keyboard event handler for RealTypeCoach."""

import time
import pyatspi
import pyatspi.registry as registry
from typing import Callable, Optional, Any
from queue import Queue
from dataclasses import dataclass
import threading

from core.burst_detector import BurstDetector, Burst
from utils.keycodes import get_key_name


@dataclass
class KeyEvent:
    """Represents a keyboard event."""
    keycode: int
    key_name: str
    timestamp_ms: int
    event_type: str  # 'press' or 'release'
    app_name: str
    is_password_field: bool


class EventHandler:
    """Handles AT-SPI keyboard events."""

    ROLE_PASSWORD_TEXT = 40

    def __init__(self, event_queue: Queue[KeyEvent],
                 layout_getter: Callable[[], str],
                 on_password_field: Optional[Callable[[bool], None]] = None):
        """Initialize event handler.

        Args:
            event_queue: Queue to send events to
            layout_getter: Function to get current keyboard layout
            on_password_field: Callback when entering/leaving password field
        """
        self.event_queue = event_queue
        self.layout_getter = layout_getter
        self.on_password_field = on_password_field
        self.running = False
        self.current_app_name: Optional[str] = None
        self.in_password_field = False
        self.thread: Optional[threading.Thread] = None
        self.registry = None  # Store Registry instance

    def start(self) -> None:
        """Start listening for keyboard events in background thread."""
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._run_listener, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        """Stop listening for keyboard events."""
        self.running = False
        if self.thread:
            # Use stored instance reference
            if self.registry:
                self.registry.deregisterKeystrokeListener(
                    self._on_keyboard_event
                )
            self.registry.stop()
            self.registry = None

    def _on_keyboard_event(self, event: Any) -> None:
        """Handle keyboard event from AT-SPI."""
        if not self.running:
            return

        try:
            timestamp_ms = int(time.time() * 1000)
            layout = self.layout_getter()

            keycode = event.event_code
            key_name = get_key_name(keycode, layout)
            event_type = 'press' if event.event_string == 'press' else 'release'

            if event_type == 'press':
                self._queue_key_event(keycode, key_name, timestamp_ms, event_type)

        except (AttributeError, TypeError, ValueError) as e:
            print(f"Error processing keyboard event: {e}")

    def _queue_key_event(self, keycode: int, key_name: str,
                        timestamp_ms: int, event_type: str) -> None:
        """Queue a key event."""
        key_event = KeyEvent(
            keycode=keycode,
            key_name=key_name,
            timestamp_ms=timestamp_ms,
            event_type=event_type,
            app_name=self.current_app_name or 'unknown',
            is_password_field=self.in_password_field
        )

        try:
            self.event_queue.put(key_event, block=False)
        except:
            pass  # Queue full, skip this event

    def _on_focus_event(self, event: Any) -> None:
        """Handle focus event from AT-SPI."""
        try:
            accessible = event.source
            role = accessible.get_role()

            if role == self.ROLE_PASSWORD_TEXT:
                if not self.in_password_field:
                    self.in_password_field = True
                    if self.on_password_field:
                        self.on_password_field(True)
                    print("Entered password field - monitoring paused")
            elif self.in_password_field and role != self.ROLE_PASSWORD_TEXT:
                self.in_password_field = False
                if self.on_password_field:
                    self.on_password_field(False)
                print("Exited password field - monitoring resumed")

            self.current_app_name = accessible.get_application().get_name()

        except (AttributeError, TypeError) as e:
            print(f"Error processing focus event: {e}")

    def get_state(self) -> dict:
        """Get current handler state.

        Returns:
            Dictionary with state information
        """
        return {
            'running': self.running,
            'current_app': self.current_app_name,
            'in_password_field': self.in_password_field,
            'queue_size': self.event_queue.qsize(),
        }
