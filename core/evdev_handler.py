"""evdev keyboard event handler for RealTypeCoach (Wayland-compatible)."""

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from queue import Full, Queue
from select import select
from typing import TYPE_CHECKING

try:
    from evdev import InputDevice, ecodes, list_devices

    EVDEV_AVAILABLE = True
except ImportError:
    EVDEV_AVAILABLE = False
    # Type stub for when evdev is not available
    if TYPE_CHECKING:
        from evdev import InputDevice

from utils.keycodes import get_key_name

log = logging.getLogger("realtypecoach.evdev")


@dataclass
class KeyEvent:
    """Represents a keyboard event."""

    keycode: int
    key_name: str
    timestamp_ms: int


class EvdevHandler:
    """Handles keyboard events using evdev (works on Wayland)."""

    def __init__(
        self,
        event_queue: Queue[KeyEvent],
        layout_getter: Callable[[], str],
        stats_panel_visible_getter: Callable[[], bool] | None = None,
    ):
        """Initialize evdev event handler.

        Args:
            event_queue: Queue to send events to
            layout_getter: Function to get current keyboard layout
            stats_panel_visible_getter: Optional function to check if stats panel is visible
        """
        if not EVDEV_AVAILABLE:
            raise ImportError(
                "evdev module is not installed. Install it with: sudo apt install python3-evdev"
            )

        self.event_queue = event_queue
        self.layout_getter = layout_getter
        self.stats_panel_visible_getter = stats_panel_visible_getter
        self._stats_panel_visible = False
        self.running = False
        self.thread: threading.Thread | None = None
        self.devices: list[InputDevice] = []
        self.device_paths: list[str] = []
        self._event_count: int = 0
        self._drop_count: int = 0
        self._stop_event = threading.Event()

    def _find_keyboard_devices(self) -> list["InputDevice"]:
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
                        ecodes.KEY_A <= code <= ecodes.KEY_Z
                        or code in [ecodes.KEY_SPACE, ecodes.KEY_ENTER, ecodes.KEY_ESC]
                        for code in caps
                    )
                    if has_letter_keys:
                        keyboards.append(device)
                        log.info(f"Found keyboard: {device.name} at {path}")
            except PermissionError:
                log.error(
                    f"Permission denied accessing {path}. You may need to be in the 'input' group."
                )
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
            raise RuntimeError(
                "No keyboard devices found. Make sure you're in the 'input' group: sudo usermod -aG input $USER"
            )

        self.device_paths = [device.path for device in self.devices]
        self.running = True
        self._stop_event.clear()
        self.thread = threading.Thread(target=self._run_listener, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        """Stop listening for keyboard events."""
        self.running = False
        self._stop_event.set()
        # Wait for listener thread to finish
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)

    def set_stats_panel_visible(self, visible: bool) -> None:
        """Set stats panel visibility for adaptive polling.

        Args:
            visible: Whether the stats panel is visible
        """
        self._stats_panel_visible = visible

    def _run_listener(self) -> None:
        """Main event loop that reads from devices."""
        # Reopen devices in this thread
        devices = []
        consecutive_empty_selects = 0
        max_empty_selects = 10  # After 10 consecutive empty selects, add backoff

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

            while not self._stop_event.is_set():
                # Filter out any bad devices before select
                valid_devices = [d for d in devices if self._is_device_valid(d)]
                if len(valid_devices) < len(devices):
                    log.warning(f"Removed {len(devices) - len(valid_devices)} invalid device(s)")
                    devices = valid_devices
                    # Update self.devices for consistency
                    self.devices = devices

                # Check if we still have devices
                if not devices:
                    log.error("No valid devices remaining, exiting listener thread")
                    return

                # Use adaptive timeout: block indefinitely when stats panel hidden,
                # use 1s timeout when visible for responsive updates
                is_visible = (
                    self.stats_panel_visible_getter()
                    if self.stats_panel_visible_getter
                    else self._stats_panel_visible
                )
                timeout = 1.0 if is_visible else None

                try:
                    r, _, _ = select(devices, [], [], timeout)
                except OSError as e:
                    # select() failed - likely bad file descriptor
                    log.error(f"select() failed: {e}, attempting to recover")
                    # Find and remove bad device
                    devices = self._remove_bad_devices(devices, e)
                    continue  # Retry with cleaned device list

                # Defensive busy-loop prevention
                if not r:
                    consecutive_empty_selects += 1
                    # If select keeps returning empty, add exponential backoff
                    if consecutive_empty_selects > max_empty_selects:
                        backoff = min(5.0, 0.1 * (consecutive_empty_selects - max_empty_selects))
                        log.warning(
                            f"Select returned empty {consecutive_empty_selects} times, "
                            f"backing off {backoff:.1f}s"
                        )
                        self._stop_event.wait(backoff)
                else:
                    consecutive_empty_selects = 0  # Reset on successful select

                for device in r:
                    if not self.running:
                        break
                    try:
                        for event in device.read():
                            if event.type == ecodes.EV_KEY:
                                self._process_key_event(event)
                    except OSError as e:
                        # Device disconnected or error - remove it from list
                        log.warning(
                            f"Device {device.name} at {device.path} failed: {e}, removing from device list"
                        )
                        if device in devices:
                            devices.remove(device)
                        # Close the bad device
                        try:
                            device.close()
                        except Exception:
                            pass
                        continue

        except Exception:
            log.exception("Error in listener thread")
        finally:
            # Close devices opened in this thread
            for device in devices:
                try:
                    device.close()
                except Exception as e:
                    log.error(f"Error closing device: {e}")

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
                event_type = "press"
            elif event.value == 0:
                event_type = "release"
            else:
                return  # Ignore repeat events

            # Log first few events for debugging (sanitize key_name to prevent logging sensitive data)
            if self._event_count < 5:
                self._event_count += 1
                # Don't log actual letter/number characters - just log the type of key
                if len(key_name) == 1:
                    key_type = "CHARACTER" if key_name.isalnum() else key_name
                else:
                    key_type = key_name  # Special keys like SPACE, ENTER are safe to log
                log.info(f"Received key event: {key_type} ({keycode}) - {event_type}")

            # Only queue press events to reduce queue size
            if event_type == "press":
                self._queue_key_event(keycode, key_name, timestamp_ms)

        except Exception as e:
            # Catch all exceptions to prevent event loop crashes
            log.error(f"Error processing keyboard event (code={getattr(event, 'code', '?')}): {e}")

    def _queue_key_event(self, keycode: int, key_name: str, timestamp_ms: int) -> None:
        """Queue a key event."""
        key_event = KeyEvent(keycode=keycode, key_name=key_name, timestamp_ms=timestamp_ms)

        try:
            self.event_queue.put(key_event, block=False)
        except Full:
            # Queue full - log this so user knows events are being dropped
            self._drop_count += 1
            # Log every 100th dropped event to avoid spam
            if self._drop_count % 100 == 1:
                log.warning(
                    f"Queue full! Dropped {self._drop_count} events. Queue size: {self.event_queue.qsize()}"
                )

    def _is_device_valid(self, device) -> bool:
        """Check if a device file descriptor is still valid.

        Args:
            device: InputDevice to check

        Returns:
            True if device FD is valid, False otherwise
        """
        try:
            # Try to get the file descriptor number
            fd = device.fileno()
            # Check if FD is valid using fcntl
            import fcntl

            fcntl.fcntl(fd, fcntl.F_GETFL)
            return True
        except (OSError, AttributeError):
            return False

    def _remove_bad_devices(self, devices: list, error: OSError) -> list:
        """Remove bad devices from list after select() failure.

        Args:
            devices: List of InputDevice objects
            error: The OSError that occurred

        Returns:
            Filtered list with only valid devices
        """
        valid_devices = []
        for device in devices:
            if self._is_device_valid(device):
                valid_devices.append(device)
            else:
                log.warning(f"Removing invalid device: {device.name} at {device.path}")
                try:
                    device.close()
                except Exception:
                    pass

        # Also update self.devices for consistency
        self.devices = valid_devices
        return valid_devices

    def get_state(self) -> dict:
        """Get current handler state.

        Returns:
            Dictionary with state information
        """
        return {
            "running": self.running,
            "queue_size": self.event_queue.qsize(),
            "devices": len(self.devices),
            "handler_type": "evdev",
        }
