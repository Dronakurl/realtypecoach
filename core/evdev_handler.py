"""evdev keyboard event handler for RealTypeCoach (Wayland-compatible)."""

import time
import threading
import logging
from typing import Callable, Optional, List
from queue import Queue
from dataclasses import dataclass

try:
    from evdev import InputDevice, list_devices, categorize, ecodes
    EVDEV_AVAILABLE = True
except ImportError:
    EVDEV_AVAILABLE = False

from core.burst_detector import BurstDetector, Burst
from utils.keycodes import get_key_name

log = logging.getLogger('realtypecoach.evdev')


@dataclass
class KeyEvent:
    """Represents a keyboard event."""
    keycode: int
    key_name: str
    timestamp_ms: int
    event_type: str  # 'press' or 'release'
    app_name: str


class EvdevHandler:
    """Handles keyboard events using evdev (works on Wayland)."""

    def __init__(self, event_queue: Queue[KeyEvent],
                 layout_getter: Callable[[], str]):
        """Initialize evdev event handler.

        Args:
            event_queue: Queue to send events to
            layout_getter: Function to get current keyboard layout
        """
        if not EVDEV_AVAILABLE:
            raise ImportError("evdev module is not installed. Install it with: sudo apt install python3-evdev")

        self.event_queue = event_queue
        self.layout_getter = layout_getter
        self.running = False
        self.current_app_name: Optional[str] = 'unknown'
        self.thread: Optional[threading.Thread] = None
        self.devices: List[InputDevice] = []
        self.device_paths: List[str] = []

    def _find_keyboard_devices(self) -> List[InputDevice]:
        """Find all keyboard input devices."""
        keyboards = []
        for path in list_devices():
            try:
                device = InputDevice(path)
                # Check if device has EV_KEY capability (keyboard)
                if ecodes.EV_KEY in device.capabilities():
                    # Filter out non-keyboard devices by checking for common keys
                    caps = device.capabilities()[ecodes.EV_KEY]
                    # Check if it has letter keys (A-Z) or common keys
                    has_letter_keys = any(
                        ecodes.KEY_A <= code <= ecodes.KEY_Z or
                        code in [ecodes.KEY_SPACE, ecodes.KEY_ENTER, ecodes.KEY_ESC]
                        for code in caps
                    )
                    if has_letter_keys:
                        keyboards.append(device)
                        log.info(f"Found keyboard: {device.name} at {path}")
            except PermissionError:
                log.error(f"Permission denied accessing {path}. You may need to be in the 'input' group.")
            except OSError as e:
                log.error(f"Error accessing {path}: {e}")

        return keyboards

    def start(self) -> None:
        """Start listening for keyboard events in background thread."""
        if self.running:
            return

        # Find keyboard devices
        self.devices = self._find_keyboard_devices()
        if not self.devices:
            raise RuntimeError("No keyboard devices found. Make sure you're in the 'input' group: sudo usermod -aG input $USER")

        self.device_paths = [device.path for device in self.devices]
        self.running = True
        self.thread = threading.Thread(target=self._run_listener, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        """Stop listening for keyboard events."""
        self.running = False
        # Note: We don't close devices here as they may be used elsewhere
        # The devices will be closed when the InputDevice objects are garbage collected

    def _run_listener(self) -> None:
        """Main event loop that reads from devices."""
        # Reopen devices in this thread
        devices = []
        try:
            for path in self.device_paths:
                try:
                    device = InputDevice(path)
                    devices.append(device)
                except (OSError, PermissionError) as e:
                    log.error(f"Error reopening device {path}: {e}")

            if not devices:
                log.error("No keyboard devices available in listener thread")
                return

            log.info(f"Listening on {len(devices)} keyboard device(s)...")

            while self.running:
                # Use select to efficiently wait for events from any device
                from select import select
                r, _, _ = select(devices, [], [], 0.1)

                for device in r:
                    if not self.running:
                        break
                    try:
                        for event in device.read():
                            if event.type == ecodes.EV_KEY:
                                self._process_key_event(event)
                    except OSError:
                        # Device disconnected
                        continue

        except Exception as e:
            log.error(f"Error in listener thread: {e}")
            import traceback
            traceback.print_exc()

    def _process_key_event(self, event) -> None:
        """Process a single key event from evdev."""
        try:
            timestamp_ms = int(event.timestamp() * 1000)
            layout = self.layout_getter()

            # Get keycode and key name
            keycode = event.code
            key_name = get_key_name(keycode, layout)

            # Determine event type (press or release)
            # event.value: 0 = release, 1 = press, 2 = repeat
            if event.value == 1:
                event_type = 'press'
            elif event.value == 0:
                event_type = 'release'
            else:
                return  # Ignore repeat events

            # Log first few events for debugging
            if not hasattr(self, '_event_count'):
                self._event_count = 0
            if self._event_count < 5:
                self._event_count += 1
                log.info(f"Received key event: {key_name} ({keycode}) - {event_type}")

            # Only queue press events to reduce queue size
            if event_type == 'press':
                self._queue_key_event(keycode, key_name, timestamp_ms, event_type)

        except (AttributeError, TypeError, ValueError) as e:
            log.error(f"Error processing keyboard event: {e}")

    def _queue_key_event(self, keycode: int, key_name: str,
                        timestamp_ms: int, event_type: str) -> None:
        """Queue a key event."""
        key_event = KeyEvent(
            keycode=keycode,
            key_name=key_name,
            timestamp_ms=timestamp_ms,
            event_type=event_type,
            app_name=self.current_app_name or 'unknown'
        )

        try:
            self.event_queue.put(key_event, block=False)
        except:
            # Queue full - log this so user knows events are being dropped
            if not hasattr(self, '_drop_count'):
                self._drop_count = 0
            self._drop_count += 1
            # Log every 100th dropped event to avoid spam
            if self._drop_count % 100 == 1:
                log.warning(f"Queue full! Dropped {self._drop_count} events. Queue size: {self.event_queue.qsize()}")

    def get_state(self) -> dict:
        """Get current handler state.

        Returns:
            Dictionary with state information
        """
        return {
            'running': self.running,
            'current_app': self.current_app_name,
            'queue_size': self.event_queue.qsize(),
            'devices': len(self.devices),
            'handler_type': 'evdev',
        }
