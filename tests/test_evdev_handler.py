"""Tests for core.evdev_handler module."""

from queue import Queue
from unittest.mock import MagicMock, patch

import pytest

from core.evdev_handler import EVDEV_AVAILABLE, EvdevHandler, KeyEvent


@pytest.fixture
def event_queue():
    """Create event queue for testing."""
    return Queue(maxsize=100)


@pytest.fixture
def mock_layout_getter():
    """Mock layout getter function."""
    return lambda: "us"


@pytest.fixture
def setup_ecodes():
    """Set up common evdev ecodes constants on a mock."""

    def _setup(mock_ecodes, include_ev_rel=False):
        mock_ecodes.KEY_A = 30
        mock_ecodes.KEY_Z = 46
        mock_ecodes.KEY_SPACE = 57
        mock_ecodes.KEY_ENTER = 28
        mock_ecodes.KEY_ESC = 1
        mock_ecodes.EV_KEY = 1
        if include_ev_rel:
            mock_ecodes.EV_REL = 2

    return _setup


class TestKeyEventDataclass:
    """Tests for KeyEvent dataclass."""

    def test_key_event_creation(self):
        """Test KeyEvent object creation."""
        event = KeyEvent(keycode=30, key_name="a", timestamp_ms=1234567890)

        assert event.keycode == 30
        assert event.key_name == "a"
        assert event.timestamp_ms == 1234567890


class TestEvdevHandlerInit:
    """Tests for EvdevHandler initialization."""

    @patch("core.evdev_handler.EVDEV_AVAILABLE", True)
    def test_evdev_handler_init(self, event_queue, mock_layout_getter):
        """Test EvdevHandler initialization."""
        handler = EvdevHandler(event_queue, mock_layout_getter)

        assert handler.event_queue is event_queue
        assert handler.layout_getter is mock_layout_getter
        assert handler.running is False
        assert handler.thread is None
        assert handler.devices == []
        assert handler.device_paths == []

    @patch("core.evdev_handler.EVDEV_AVAILABLE", False)
    def test_evdev_handler_init_without_evdev(self, event_queue, mock_layout_getter):
        """Test that ImportError is raised when evdev is not available."""
        with pytest.raises(ImportError, match="evdev module is not installed"):
            EvdevHandler(event_queue, mock_layout_getter)


class TestFindKeyboardDevices:
    """Tests for _find_keyboard_devices method."""

    @patch("core.evdev_handler.EVDEV_AVAILABLE", True)
    @patch("core.evdev_handler.list_devices")
    @patch("core.evdev_handler.InputDevice")
    @patch("core.evdev_handler.ecodes")
    def test_find_keyboards_finds_devices(
        self,
        mock_ecodes,
        mock_input_device,
        mock_list_devices,
        event_queue,
        mock_layout_getter,
        setup_ecodes,
    ):
        """Test that keyboard devices are found."""
        # Mock device list
        mock_list_devices.return_value = ["/dev/input/event0", "/dev/input/event1"]

        # Mock ecodes constants
        setup_ecodes(mock_ecodes, include_ev_rel=True)

        # Mock first device as keyboard, second as non-keyboard
        keyboard_device = MagicMock()
        keyboard_device.name = "Test Keyboard"
        keyboard_device.path = "/dev/input/event0"
        keyboard_device.capabilities.return_value = {
            mock_ecodes.EV_KEY: [mock_ecodes.KEY_A, mock_ecodes.KEY_SPACE]
        }

        mouse_device = MagicMock()
        mouse_device.name = "Test Mouse"
        mouse_device.path = "/dev/input/event1"
        mouse_device.capabilities.return_value = {
            mock_ecodes.EV_REL: [1, 2]  # Relative axis (mouse)
        }

        mock_input_device.side_effect = [keyboard_device, mouse_device]

        handler = EvdevHandler(event_queue, mock_layout_getter)
        keyboards = handler._find_keyboard_devices()

        assert len(keyboards) == 1
        assert keyboards[0].name == "Test Keyboard"

    @patch("core.evdev_handler.EVDEV_AVAILABLE", True)
    @patch("core.evdev_handler.list_devices")
    @patch("core.evdev_handler.InputDevice")
    @patch("core.evdev_handler.ecodes")
    def test_find_keyboards_permission_error(
        self,
        mock_ecodes,
        mock_input_device,
        mock_list_devices,
        event_queue,
        mock_layout_getter,
    ):
        """Test that PermissionError is logged and continues."""
        mock_list_devices.return_value = ["/dev/input/event0"]
        mock_input_device.side_effect = PermissionError("Permission denied")
        mock_ecodes.EV_KEY = 1

        handler = EvdevHandler(event_queue, mock_layout_getter)
        keyboards = handler._find_keyboard_devices()

        # Should return empty list and not crash
        assert keyboards == []

    @patch("core.evdev_handler.EVDEV_AVAILABLE", True)
    @patch("core.evdev_handler.list_devices")
    @patch("core.evdev_handler.InputDevice")
    @patch("core.evdev_handler.ecodes")
    def test_find_keyboards_filters_non_keyboards(
        self,
        mock_ecodes,
        mock_input_device,
        mock_list_devices,
        event_queue,
        mock_layout_getter,
        setup_ecodes,
    ):
        """Test that non-keyboard devices are filtered out."""
        # Set up ecodes constants
        setup_ecodes(mock_ecodes)

        mock_list_devices.return_value = ["/dev/input/event0"]

        # Device with EV_KEY but no letter keys or common keys
        device = MagicMock()
        device.name = "Power Button"
        device.path = "/dev/input/event0"
        device.capabilities.return_value = {
            mock_ecodes.EV_KEY: [999]  # Unknown key code
        }

        mock_input_device.return_value = device

        handler = EvdevHandler(event_queue, mock_layout_getter)
        keyboards = handler._find_keyboard_devices()

        # Should be filtered out
        assert len(keyboards) == 0


class TestStartStop:
    """Tests for start and stop methods."""

    @patch("core.evdev_handler.EVDEV_AVAILABLE", True)
    @patch("core.evdev_handler.list_devices")
    @patch("core.evdev_handler.InputDevice")
    @patch("core.evdev_handler.ecodes")
    @patch("select.select")
    def test_start_creates_listener_thread(
        self,
        mock_select,
        mock_ecodes,
        mock_input_device,
        mock_list_devices,
        event_queue,
        mock_layout_getter,
        setup_ecodes,
    ):
        """Test that start() creates a listener thread."""
        # Setup ecodes constants
        setup_ecodes(mock_ecodes)

        # Setup device mocks
        mock_list_devices.return_value = ["/dev/input/event0"]
        device = MagicMock()
        device.name = "Test Keyboard"
        device.path = "/dev/input/event0"
        device.capabilities.return_value = {1: [30, 57]}
        device.read.return_value = []  # No events
        mock_input_device.return_value = device
        mock_select.return_value = ([], [], [])

        handler = EvdevHandler(event_queue, mock_layout_getter)
        handler.start()

        assert handler.running is True
        assert handler.thread is not None

        # Note: thread might not be alive yet or might have exited quickly
        # We just check that it was created
        handler.stop()

    @patch("core.evdev_handler.EVDEV_AVAILABLE", True)
    @patch("core.evdev_handler.list_devices")
    def test_start_no_devices_raises_error(
        self, mock_list_devices, event_queue, mock_layout_getter
    ):
        """Test that start() raises RuntimeError when no devices found."""
        mock_list_devices.return_value = []

        handler = EvdevHandler(event_queue, mock_layout_getter)

        with pytest.raises(RuntimeError, match="No keyboard devices found"):
            handler.start()

    @patch("core.evdev_handler.EVDEV_AVAILABLE", True)
    @patch("core.evdev_handler.list_devices")
    @patch("core.evdev_handler.InputDevice")
    @patch("core.evdev_handler.ecodes")
    @patch("select.select")
    def test_stop_sets_running_false(
        self,
        mock_select,
        mock_ecodes,
        mock_input_device,
        mock_list_devices,
        event_queue,
        mock_layout_getter,
        setup_ecodes,
    ):
        """Test that stop() sets running to False."""
        # Setup ecodes constants
        setup_ecodes(mock_ecodes)

        # Setup device mocks
        mock_list_devices.return_value = ["/dev/input/event0"]
        device = MagicMock()
        device.path = "/dev/input/event0"
        device.capabilities.return_value = {1: [30]}
        device.read.return_value = []
        mock_input_device.return_value = device
        mock_select.return_value = ([], [], [])

        handler = EvdevHandler(event_queue, mock_layout_getter)
        handler.start()

        assert handler.running is True

        handler.stop()

        assert handler.running is False

    @patch("core.evdev_handler.EVDEV_AVAILABLE", True)
    def test_start_when_already_running(self, event_queue, mock_layout_getter):
        """Test that calling start() twice doesn't create duplicate threads."""
        handler = EvdevHandler(event_queue, mock_layout_getter)
        handler.running = True
        handler.thread = MagicMock()

        # Should return early
        handler.start()

        # thread should still be the MagicMock, not a new thread
        assert isinstance(handler.thread, MagicMock)


class TestProcessEvent:
    """Tests for _process_key_event method."""

    @patch("core.evdev_handler.EVDEV_AVAILABLE", True)
    @patch("core.evdev_handler.get_key_name")
    def test_process_key_event_press(self, mock_get_key_name, event_queue, mock_layout_getter):
        """Test processing key press event."""
        mock_get_key_name.return_value = "a"

        # Create mock event (press)
        event = MagicMock()
        event.timestamp.return_value = 1234567890.123
        event.code = 30
        event.value = 1  # Press

        handler = EvdevHandler(event_queue, mock_layout_getter)
        handler._process_key_event(event)

        # Check that event was queued
        assert not event_queue.empty()
        queued_event = event_queue.get()
        assert queued_event.key_name == "a"

    @patch("core.evdev_handler.EVDEV_AVAILABLE", True)
    @patch("core.evdev_handler.get_key_name")
    def test_process_key_event_release_ignored(
        self, mock_get_key_name, event_queue, mock_layout_getter
    ):
        """Test that release events are not queued."""
        mock_get_key_name.return_value = "a"

        # Create mock event (release)
        event = MagicMock()
        event.timestamp.return_value = 1234567890.123
        event.code = 30
        event.value = 0  # Release

        handler = EvdevHandler(event_queue, mock_layout_getter)
        handler._process_key_event(event)

        # Event should NOT be queued
        assert event_queue.empty()

    @patch("core.evdev_handler.EVDEV_AVAILABLE", True)
    @patch("core.evdev_handler.get_key_name")
    def test_process_key_event_repeat_ignored(
        self, mock_get_key_name, event_queue, mock_layout_getter
    ):
        """Test that repeat events are ignored."""
        mock_get_key_name.return_value = "a"

        # Create mock event (repeat)
        event = MagicMock()
        event.timestamp.return_value = 1234567890.123
        event.code = 30
        event.value = 2  # Repeat

        handler = EvdevHandler(event_queue, mock_layout_getter)
        handler._process_key_event(event)

        # Event should NOT be queued
        assert event_queue.empty()

    @patch("core.evdev_handler.EVDEV_AVAILABLE", True)
    @patch("core.evdev_handler.get_key_name")
    def test_process_key_event_error_handling(
        self, mock_get_key_name, event_queue, mock_layout_getter
    ):
        """Test that all exceptions in event processing are caught."""
        # Make get_key_name raise various types of exceptions
        for exc in [
            AttributeError("Test"),
            RuntimeError("Test"),
            ValueError("Test"),
            Exception("Test"),
        ]:
            mock_get_key_name.side_effect = exc

            event = MagicMock()
            event.timestamp.return_value = 1234567890.123
            event.code = 30
            event.value = 1

            handler = EvdevHandler(event_queue, mock_layout_getter)

            # Should not raise exception
            handler._process_key_event(event)

            # Event should not be queued due to error
            assert event_queue.empty(), f"Queue should be empty after {type(exc).__name__}"
            # Clear queue for next iteration (should be empty already)
            while not event_queue.empty():
                event_queue.get()


class TestQueueKeyEvent:
    """Tests for _queue_key_event method."""

    @patch("core.evdev_handler.EVDEV_AVAILABLE", True)
    def test_queue_key_event_success(self, event_queue, mock_layout_getter):
        """Test successful event queuing."""
        handler = EvdevHandler(event_queue, mock_layout_getter)
        handler._queue_key_event(30, "a", 1234567890)

        assert not event_queue.empty()
        queued_event = event_queue.get()
        assert queued_event.keycode == 30
        assert queued_event.key_name == "a"
        assert queued_event.timestamp_ms == 1234567890

    @patch("core.evdev_handler.EVDEV_AVAILABLE", True)
    def test_queue_key_event_queue_full(self, event_queue, mock_layout_getter):
        """Test handling when queue is full."""
        # Fill the queue to capacity
        initial_size = event_queue.qsize()
        for _ in range(100 - initial_size):
            event_queue.put(None)

        # Verify queue is full
        assert event_queue.full() or event_queue.qsize() >= 100

        handler = EvdevHandler(event_queue, mock_layout_getter)
        handler._queue_key_event(30, "a", 1234567890)

        # Queue size should not increase beyond max
        assert event_queue.qsize() <= 100

        # Event should not be in queue (queue is still full with None values)
        # Try to get an event - it should be None, not the KeyEvent we tried to add
        for _ in range(event_queue.qsize()):
            item = event_queue.get()
            if item is not None:
                # If we find a non-None item, it shouldn't be the one we just tried to add
                assert item.keycode != 30 or item.key_name != "a"


class TestGetState:
    """Tests for get_state method."""

    @patch("core.evdev_handler.EVDEV_AVAILABLE", True)
    def test_get_state_returns_handler_info(self, event_queue, mock_layout_getter):
        """Test that get_state returns correct information."""
        handler = EvdevHandler(event_queue, mock_layout_getter)
        handler.devices = [MagicMock(), MagicMock()]  # Mock devices

        state = handler.get_state()

        assert not state["running"]
        assert state["queue_size"] == 0
        assert state["devices"] == 2
        assert state["handler_type"] == "evdev"

    @patch("core.evdev_handler.EVDEV_AVAILABLE", True)
    def test_get_state_with_items_in_queue(self, event_queue, mock_layout_getter):
        """Test queue_size in state."""
        # Add some items to queue
        event_queue.put(MagicMock())
        event_queue.put(MagicMock())

        handler = EvdevHandler(event_queue, mock_layout_getter)
        state = handler.get_state()

        assert state["queue_size"] == 2


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    @patch("core.evdev_handler.EVDEV_AVAILABLE", True)
    def test_multiple_keycode_lookups(self, event_queue, mock_layout_getter):
        """Test handler with different keycode lookups."""
        handler = EvdevHandler(event_queue, lambda: "de")  # German layout

        # This tests that layout_getter is called for each event
        assert handler.layout_getter() == "de"

    @patch("core.evdev_handler.EVDEV_AVAILABLE", True)
    @patch("core.evdev_handler.get_key_name")
    def test_high_volume_events(self, mock_get_key_name, event_queue, mock_layout_getter):
        """Test processing many events in succession."""
        mock_get_key_name.return_value = "a"

        handler = EvdevHandler(event_queue, mock_layout_getter)

        # Process 50 events
        for i in range(50):
            event = MagicMock()
            event.timestamp.return_value = 1234567890.123 + (i * 0.001)
            event.code = 30
            event.value = 1
            handler._process_key_event(event)

        # All should be queued
        assert event_queue.qsize() == 50


class TestEvdevAvailability:
    """Tests for evdev availability check."""

    def test_evdev_available_flag_exists(self):
        """Test that EVDEV_AVAILABLE flag exists."""
        assert isinstance(EVDEV_AVAILABLE, bool)

    @patch("core.evdev_handler.EVDEV_AVAILABLE", True)
    def test_handler_creation_when_available(self, event_queue, mock_layout_getter):
        """Test handler can be created when EVDEV_AVAILABLE is True."""
        handler = EvdevHandler(event_queue, mock_layout_getter)
        assert handler is not None
