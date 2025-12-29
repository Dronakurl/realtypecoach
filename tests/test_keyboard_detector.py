"""Tests for utils.keyboard_detector module."""

from unittest.mock import patch, MagicMock, mock_open
import time

from utils.keyboard_detector import get_current_layout, get_available_layouts, LayoutMonitor


class TestGetCurrentLayout:
    """Tests for get_current_layout function."""

    @patch.dict('os.environ', {'XKB_DEFAULT_LAYOUT': 'de'})
    def test_layout_from_env_variable_single(self):
        """Test XKB_DEFAULT_LAYOUT with single layout."""
        assert get_current_layout() == 'de'

    @patch.dict('os.environ', {'XKB_DEFAULT_LAYOUT': 'us,de,gb'})
    def test_layout_from_env_variable_multiple(self):
        """Test XKB_DEFAULT_LAYOUT with multiple layouts (returns first)."""
        assert get_current_layout() == 'us'

    @patch.dict('os.environ', {'XKB_DEFAULT_LAYOUT': ' de '})
    def test_layout_from_env_variable_whitespace(self):
        """Test XKB_DEFAULT_LAYOUT with whitespace is stripped."""
        assert get_current_layout() == 'de'

    @patch('subprocess.run')
    @patch.dict('os.environ', {}, clear=True)
    def test_layout_from_localectl(self, mock_run):
        """Test layout detection from localectl status."""
        mock_result = MagicMock()
        mock_result.stdout = 'X11 Layout: us\nVC Keymap: us\n'
        mock_run.return_value = mock_result

        assert get_current_layout() == 'us'

    @patch('subprocess.run')
    @patch.dict('os.environ', {}, clear=True)
    def test_layout_from_localectl_de(self, mock_run):
        """Test German layout from localectl."""
        mock_result = MagicMock()
        mock_result.stdout = 'X11 Layout: de\nVC Keymap: de\n'
        mock_run.return_value = mock_result

        assert get_current_layout() == 'de'

    @patch('builtins.open', new_callable=mock_open, read_data='XKBLAYOUT="de"')
    @patch('subprocess.run')
    @patch.dict('os.environ', {}, clear=True)
    def test_layout_from_etc_keyboard_double_quotes(self, mock_run, mock_file):
        """Test reading from /etc/default/keyboard with double quotes."""
        # Make localectl fail
        mock_run.side_effect = FileNotFoundError()

        assert get_current_layout() == 'de'

    @patch('builtins.open', new_callable=mock_open, read_data="XKBLAYOUT='us'")
    @patch('subprocess.run')
    @patch.dict('os.environ', {}, clear=True)
    def test_layout_from_etc_keyboard_single_quotes(self, mock_run, mock_file):
        """Test reading from /etc/default/keyboard with single quotes."""
        mock_run.side_effect = FileNotFoundError()

        assert get_current_layout() == 'us'

    @patch('builtins.open', new_callable=mock_open, read_data='XKBLAYOUT=us')
    @patch('subprocess.run')
    @patch.dict('os.environ', {}, clear=True)
    def test_layout_from_etc_keyboard_no_quotes(self, mock_run, mock_file):
        """Test reading from /etc/default/keyboard without quotes."""
        mock_run.side_effect = FileNotFoundError()

        assert get_current_layout() == 'us'

    @patch('builtins.open', new_callable=mock_open, read_data='XKBLAYOUT="us,de,gb"')
    @patch('subprocess.run')
    @patch.dict('os.environ', {}, clear=True)
    def test_layout_from_etc_keyboard_multiple(self, mock_run, mock_file):
        """Test /etc/default/keyboard with multiple layouts."""
        mock_run.side_effect = FileNotFoundError()

        assert get_current_layout() == 'us'

    @patch('subprocess.run')
    @patch('builtins.open', side_effect=FileNotFoundError())
    @patch.dict('os.environ', {}, clear=True)
    def test_layout_from_setxkbmap(self, mock_open, mock_run):
        """Test layout detection from setxkbmap -query."""
        # First call to localectl fails, second call to setxkbmap succeeds
        mock_run.side_effect = [
            FileNotFoundError(),  # localectl fails
            MagicMock(stdout='layout:     gb\n')  # setxkbmap succeeds
        ]

        assert get_current_layout() == 'gb'

    @patch('subprocess.run')
    @patch('builtins.open')
    @patch.dict('os.environ', {}, clear=True)
    def test_layout_fallback_to_us(self, mock_open, mock_run):
        """Test ultimate fallback to 'us' when all methods fail."""
        mock_run.side_effect = FileNotFoundError()
        mock_open.side_effect = FileNotFoundError()

        assert get_current_layout() == 'us'


class TestGetAvailableLayouts:
    """Tests for get_available_layouts function."""

    @patch.dict('os.environ', {'XKB_DEFAULT_LAYOUT': 'us'})
    def test_single_layout_from_env(self):
        """Test single layout from environment variable."""
        result = get_available_layouts()
        assert result == ['us']

    @patch.dict('os.environ', {'XKB_DEFAULT_LAYOUT': 'us,de,gb'})
    def test_multiple_layouts_from_env(self):
        """Test multiple layouts from environment variable."""
        result = get_available_layouts()
        assert result == ['us', 'de', 'gb']

    @patch.dict('os.environ', {'XKB_DEFAULT_LAYOUT': ' us , de , gb '})
    def test_multiple_layouts_with_whitespace(self):
        """Test multiple layouts with extra whitespace."""
        result = get_available_layouts()
        assert result == ['us', 'de', 'gb']

    @patch('subprocess.run')
    @patch.dict('os.environ', {}, clear=True)
    def test_multiple_layouts_from_localectl(self, mock_run):
        """Test multiple layouts from localectl."""
        mock_result = MagicMock()
        mock_result.stdout = 'X11 Layout: us,de\n'
        mock_run.return_value = mock_result

        result = get_available_layouts()
        assert result == ['us', 'de']

    @patch('subprocess.run')
    @patch('builtins.open', new_callable=mock_open, read_data='XKBLAYOUT="de,us"')
    @patch.dict('os.environ', {}, clear=True)
    def test_multiple_layouts_from_etc_keyboard(self, mock_file, mock_run):
        """Test multiple layouts from /etc/default/keyboard."""
        mock_run.side_effect = FileNotFoundError()

        result = get_available_layouts()
        assert result == ['de', 'us']

    @patch('subprocess.run')
    @patch('builtins.open')
    @patch.dict('os.environ', {}, clear=True)
    def test_fallback_to_single_us(self, mock_open, mock_run):
        """Test fallback to single ['us'] layout."""
        mock_run.side_effect = FileNotFoundError()
        mock_open.side_effect = FileNotFoundError()

        result = get_available_layouts()
        assert result == ['us']


class TestLayoutMonitor:
    """Tests for LayoutMonitor class."""

    def test_layout_monitor_init(self):
        """Test LayoutMonitor initialization."""
        callback = MagicMock()
        monitor = LayoutMonitor(callback, poll_interval=30)

        assert monitor.callback is callback
        assert monitor.poll_interval == 30
        assert monitor.running is False
        assert monitor.thread is None
        # Should call get_current_layout to get initial layout
        # We can't test the exact value without mocking

    @patch('utils.keyboard_detector.get_current_layout')
    def test_layout_monitor_init_gets_initial_layout(self, mock_get_layout):
        """Test that LayoutMonitor gets initial layout on init."""
        mock_get_layout.return_value = 'de'

        callback = MagicMock()
        monitor = LayoutMonitor(callback, poll_interval=30)

        assert monitor.current_layout == 'de'
        mock_get_layout.assert_called_once()

    @patch('utils.keyboard_detector.get_current_layout')
    def test_layout_monitor_detects_change(self, mock_get_layout):
        """Test that layout change triggers callback."""
        # Start with 'us'
        mock_get_layout.return_value = 'us'
        callback = MagicMock()
        monitor = LayoutMonitor(callback, poll_interval=0.1)

        # Simulate layout change
        mock_get_layout.return_value = 'de'

        # Start monitoring
        monitor.start()
        time.sleep(0.2)  # Wait for at least one poll

        monitor.stop()

        # Callback should have been called with 'de'
        callback.assert_called_with('de')

    @patch('utils.keyboard_detector.get_current_layout')
    def test_layout_monitor_no_change_no_callback(self, mock_get_layout):
        """Test that no layout change doesn't trigger callback."""
        mock_get_layout.return_value = 'us'
        callback = MagicMock()
        monitor = LayoutMonitor(callback, poll_interval=0.1)

        monitor.start()
        time.sleep(0.2)
        monitor.stop()

        # Callback should not have been called (layout didn't change)
        callback.assert_not_called()

    def test_layout_monitor_start_creates_thread(self):
        """Test that start() creates a daemon thread."""
        callback = MagicMock()
        monitor = LayoutMonitor(callback, poll_interval=0.1)

        monitor.start()

        assert monitor.running is True
        assert monitor.thread is not None
        assert monitor.thread.is_alive()
        assert monitor.thread.daemon is True

        monitor.stop()

    def test_layout_monitor_double_start(self):
        """Test that calling start() twice doesn't create duplicate threads."""
        callback = MagicMock()
        monitor = LayoutMonitor(callback, poll_interval=0.1)

        first_thread = monitor.start()
        second_thread = monitor.start()

        assert first_thread is second_thread

        monitor.stop()

    def test_layout_monitor_stop(self):
        """Test that stop() sets running to False and joins thread."""
        callback = MagicMock()
        monitor = LayoutMonitor(callback, poll_interval=0.1)

        monitor.start()
        thread = monitor.thread
        monitor.stop()

        assert monitor.running is False
        # Thread should be stopped or stopping
        assert not thread.is_alive() or thread is None

    @patch('utils.keyboard_detector.get_current_layout')
    def test_layout_monitor_callback_exception_handled(self, mock_get_layout):
        """Test that exceptions in callback are caught and handled."""
        # Return 'us' initially, then 'de' to trigger callback
        mock_get_layout.side_effect = ['us', 'de', 'de', 'de']

        def failing_callback(new_layout):
            raise RuntimeError("Test error")

        monitor = LayoutMonitor(failing_callback, poll_interval=0.1)

        # Should not raise exception
        monitor.start()
        time.sleep(0.25)  # Wait for polls
        monitor.stop()

        # Monitor should still be functional (stopped gracefully)
        assert monitor.running is False

    @patch('utils.keyboard_detector.get_current_layout')
    def test_layout_monitor_default_poll_interval(self, mock_get_layout):
        """Test that default poll interval is 60 seconds."""
        callback = MagicMock()
        monitor = LayoutMonitor(callback)

        assert monitor.poll_interval == 60
