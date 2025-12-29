#!/usr/bin/env python3
"""RealTypeCoach - KDE Wayland typing analysis application."""

import sys
import os
import time
import signal
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from queue import Queue, Empty

# Setup logging with XDG state directory
xdg_state_home = os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local' / 'state'))
log_dir = Path(xdg_state_home) / 'realtypecoach'
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / 'realtypecoach.log'

# Configure rotating file handler (5MB max, keep 5 backups)
file_handler = RotatingFileHandler(
    log_file,
    maxBytes=5*1024*1024,  # 5MB
    backupCount=5
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        file_handler,
        logging.StreamHandler()
    ]
)
log = logging.getLogger('realtypecoach')

from PyQt5.QtWidgets import QApplication, QMessageBox, QDialog  # noqa: E402
from PyQt5.QtCore import QTimer, QObject, pyqtSignal  # noqa: E402
from PyQt5.QtGui import QFont  # noqa: E402

from core.storage import Storage  # noqa: E402
from core.burst_detector import BurstDetector  # noqa: E402
from core.evdev_handler import EvdevHandler  # noqa: E402
from core.analyzer import Analyzer  # noqa: E402
from core.notification_handler import NotificationHandler  # noqa: E402
from utils.keyboard_detector import LayoutMonitor, get_current_layout  # noqa: E402
from utils.config import Config  # noqa: E402
from ui.stats_panel import StatsPanel  # noqa: E402
from ui.tray_icon import TrayIcon  # noqa: E402
from ui.settings_dialog import SettingsDialog  # noqa: E402


class Application(QObject):
    """Main application controller."""

    signal_update_stats = pyqtSignal(float, float, float)
    signal_update_slowest_keys = pyqtSignal(list)
    signal_update_fastest_keys = pyqtSignal(list)
    signal_update_hardest_words = pyqtSignal(list)
    signal_update_fastest_words_stats = pyqtSignal(list)
    signal_update_today_stats = pyqtSignal(int, int, float)
    signal_update_trend_data = pyqtSignal(list)
    signal_settings_changed = pyqtSignal(dict)

    def __init__(self):
        """Initialize application."""
        super().__init__()
        self.event_queue = Queue(maxsize=1000)
        self.running = False
        self._last_stats_update: int = 0

        self.init_data_directory()
        self.init_components()
        self.connect_signals()

    def init_data_directory(self) -> None:
        """Initialize data directory."""
        data_dir = Path.home() / '.local' / 'share' / 'realtypecoach'
        data_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = data_dir / 'typing_data.db'
        self.icon_path = data_dir / 'icon.svg'
        self.icon_paused_path = data_dir / 'icon_paused.svg'
        self.icon_stopping_path = data_dir / 'icon_stopping.svg'

        from utils.icon_generator import save_icon
        save_icon(self.icon_path, active=True)
        save_icon(self.icon_paused_path, active=False)
        save_icon(self.icon_stopping_path, stopping=True)

        print(f"Data directory: {data_dir}")
        print(f"Database: {self.db_path}")

    def init_components(self) -> None:
        """Initialize all components."""
        self.config = Config(self.db_path)
        self.storage = Storage(
            self.db_path,
            word_boundary_timeout_ms=self.config.get_int('word_boundary_timeout_ms', 1000),
            english_dict_path=self.config.get('english_dict_path', '/usr/share/dict/words'),
            german_dict_path=self.config.get('german_dict_path', '/usr/share/dict/ngerman')
        )

        current_layout = get_current_layout()
        print(f"Detected keyboard layout: {current_layout}")

        self.burst_detector = BurstDetector(
            burst_timeout_ms=self.config.get_int('burst_timeout_ms', 1000),
            high_score_min_duration_ms=self.config.get_int(
                'high_score_min_duration_ms', 10000
            ),
            duration_calculation_method=self.config.get('burst_duration_calculation', 'total_time'),
            active_time_threshold_ms=self.config.get_int('active_time_threshold_ms', 500),
            min_key_count=self.config.get_int('min_burst_key_count', 10),
            min_duration_ms=self.config.get_int('min_burst_duration_ms', 5000),
            on_burst_complete=self.on_burst_complete
        )

        self.event_handler = EvdevHandler(
            event_queue=self.event_queue,
            layout_getter=self.get_current_layout
        )

        self.analyzer = Analyzer(self.storage)

        self.notification_handler = NotificationHandler(
            summary_getter=self.analyzer.get_daily_summary,
            storage=self.storage,
            update_interval_sec=self.config.get_int('threshold_update_interval_sec', 300)
        )

        self.layout_monitor = LayoutMonitor(
            callback=self.on_layout_changed,
            poll_interval=60
        )

        self.stats_panel = StatsPanel(icon_path=str(self.icon_path))
        self.tray_icon = TrayIcon(self.stats_panel, self.icon_path, self.icon_paused_path, self.icon_stopping_path)

    def connect_signals(self) -> None:
        """Connect all signals."""
        self.signal_update_stats.connect(self.stats_panel.update_wpm)
        self.signal_update_slowest_keys.connect(self.stats_panel.update_slowest_keys)
        self.signal_update_fastest_keys.connect(self.stats_panel.update_fastest_keys)
        self.signal_update_hardest_words.connect(self.stats_panel.update_hardest_words)
        self.signal_update_fastest_words_stats.connect(self.stats_panel.update_fastest_words)
        self.signal_update_today_stats.connect(self.stats_panel.update_today_stats)
        self.signal_update_trend_data.connect(self.stats_panel.update_trend_graph)

        self.notification_handler.signal_daily_summary.connect(self.show_daily_notification)
        self.notification_handler.signal_exceptional_burst.connect(self.show_exceptional_notification)

        self.tray_icon.settings_changed.connect(self.apply_settings)
        self.tray_icon.stats_requested.connect(self.update_statistics)
        self.stats_panel.settings_requested.connect(self.show_settings_dialog)

        self.stats_panel.set_trend_data_callback(self.provide_trend_data)

    def get_current_layout(self) -> str:
        """Get current keyboard layout."""
        layout = self.config.get('keyboard_layout', 'auto')
        if layout == 'auto':
            return get_current_layout()
        return layout

    def on_burst_complete(self, burst) -> None:
        """Handle burst completion."""
        self.analyzer.process_burst(burst)

        if burst.qualifies_for_high_score:
            wpm = self._calculate_wpm(burst.key_count, burst.duration_ms)
            self.notification_handler.notify_exceptional_burst(
                wpm, burst.key_count, burst.duration_ms / 1000.0
            )

    def on_layout_changed(self, new_layout: str) -> None:
        """Handle keyboard layout change."""
        print(f"Keyboard layout changed to: {new_layout}")
        self.tray_icon.show_notification(
            "Keyboard Layout Changed",
            f"New layout: {new_layout}",
            "info"
        )

    def _calculate_wpm(self, key_count: int, duration_ms: int) -> float:
        """Calculate words per minute."""
        if duration_ms == 0:
            return 0.0

        words = key_count / 5.0
        minutes = duration_ms / 60000.0
        return words / minutes if minutes > 0 else 0.0

    def show_daily_notification(self, summary) -> None:
        """Show daily summary notification.

        Args:
            summary: DailySummary pydantic model with notification data
        """
        self.tray_icon.show_notification(summary.title, summary.message, "info")

    def show_exceptional_notification(self, wpm: float) -> None:
        """Show exceptional burst notification."""
        self.tray_icon.show_notification(
            "🚀 Exceptional Typing Speed!",
            f"{wpm:.1f} WPM - New personal best!",
            "info"
        )

    def apply_settings(self, new_settings: dict) -> None:
        """Apply new settings."""
        for key, value in new_settings.items():
            self.config.set(key, value)

        if '__clear_database__' in new_settings:
            self.storage.clear_database()
            QMessageBox.information(
                None, "Data Cleared",
                "All typing data has been deleted."
            )

        if 'export_csv_path' in new_settings:
            try:
                from datetime import datetime
                default_date = datetime.now().strftime('%Y-%m-%d')
                count = self.storage.export_to_csv(
                    Path(new_settings['export_csv_path']),
                    start_date=default_date
                )
                QMessageBox.information(
                    None, "Export Complete",
                    f"Exported {count:,} events to CSV."
                )
            except Exception as e:
                QMessageBox.critical(
                    None, "Export Failed",
                    f"Failed to export data: {e}"
                )

    def provide_trend_data(self, window_size: int) -> None:
        """Provide trend data to stats panel.

        Args:
            window_size: Number of bursts to aggregate (1-50)
        """
        import threading

        def fetch_data():
            try:
                data = self.analyzer.get_wpm_burst_sequence(window_size=window_size)
                self.signal_update_trend_data.emit(data)
            except Exception as e:
                log.error(f"Error fetching trend data: {e}")

        # Fetch in background thread to avoid blocking UI
        thread = threading.Thread(target=fetch_data, daemon=True)
        thread.start()

    def process_event_queue(self) -> None:
        """Process events from queue."""
        # Process all available events at once (non-blocking)
        processed_count = 0
        logged = False
        while processed_count < 1000:  # Increased limit to handle fast typing
            try:
                key_event = self.event_queue.get_nowait()

                # Log first few processed events for debugging
                if not logged and processed_count < 3:
                    log.info(f"Processing key event: {key_event.key_name}")
                    logged = True

                self.burst_detector.process_key_event(
                    key_event.timestamp_ms, True
                )

                self.analyzer.process_key_event(
                    key_event.keycode,
                    key_event.key_name,
                    key_event.timestamp_ms,
                    self.get_current_layout()
                )

                processed_count += 1

            except Empty:
                break  # Queue empty

        # Update stats display periodically (every 10 seconds if processing events)
        current_time = int(time.time())
        if processed_count > 0:
            if current_time - self._last_stats_update >= 10:
                self.update_statistics()
                self._last_stats_update = current_time

    def update_statistics(self) -> None:
        """Update statistics display."""
        stats = self.analyzer.get_statistics()

        self.signal_update_stats.emit(
            stats['avg_wpm'],
            stats['burst_wpm'],
            stats['personal_best_today'] or 0
        )

        slowest_keys = self.analyzer.get_slowest_keys(
            limit=self.config.get_int('slowest_keys_count', 10),
            layout=self.get_current_layout()
        )
        self.signal_update_slowest_keys.emit(slowest_keys)

        fastest_keys = self.analyzer.get_fastest_keys(
            limit=self.config.get_int('fastest_keys_count', 10),
            layout=self.get_current_layout()
        )
        self.signal_update_fastest_keys.emit(fastest_keys)

        hardest_words = self.analyzer.get_slowest_words(
            limit=10,
            layout=self.get_current_layout()
        )
        self.signal_update_hardest_words.emit(hardest_words)

        fastest_words = self.analyzer.get_fastest_words(
            limit=10,
            layout=self.get_current_layout()
        )
        self.signal_update_fastest_words_stats.emit(fastest_words)

        self.signal_update_today_stats.emit(
            stats['total_keystrokes'],
            stats['total_bursts'],
            stats['total_typing_sec']
        )

    def show_settings_dialog(self) -> None:
        """Show settings dialog."""
        current_settings = {
            'burst_timeout_ms': self.config.get_int('burst_timeout_ms', 1000),
            'burst_duration_calculation': self.config.get('burst_duration_calculation', 'total_time'),
            'active_time_threshold_ms': self.config.get_int('active_time_threshold_ms', 500),
            'high_score_min_duration_ms': self.config.get_int('high_score_min_duration_ms', 10000),
            'keyboard_layout': self.config.get('keyboard_layout', 'auto'),
            'notifications_enabled': self.config.get_bool('notifications_enabled', True),
            'exceptional_wpm_threshold': self.config.get_int('exceptional_wpm_threshold', 120),
            'notification_time_hour': self.config.get_int('notification_time_hour', 18),
            'slowest_keys_count': self.config.get_int('slowest_keys_count', 10),
            'data_retention_days': self.config.get_int('data_retention_days', -1),
            'english_dict_path': self.config.get('english_dict_path', '/usr/share/dict/words'),
            'german_dict_path': self.config.get('german_dict_path', '/usr/share/dict/ngerman'),
        }
        dialog = SettingsDialog(current_settings)
        if dialog.exec_() == QDialog.Accepted:
            new_settings = dialog.get_settings()
            self.apply_settings(new_settings)

    def start(self) -> None:
        """Start all components."""
        log.info("Starting RealTypeCoach...")

        self.running = True

        log.info("Starting event handler...")
        self.event_handler.start()

        log.info("Starting layout monitor...")
        self.layout_monitor.start()

        log.info("Starting analyzer...")
        self.analyzer.start()

        # Load and display existing statistics
        self.update_statistics()

        log.info("Starting notification handler...")
        self.notification_handler.start()

        self.process_queue_timer = QTimer()
        self.process_queue_timer.timeout.connect(self.process_event_queue)
        self.process_queue_timer.start(500)  # Check every 500ms

        self.tray_icon.show()

        self.notification_handler.set_notification_time(
            hour=self.config.get_int('notification_time_hour', 18),
            minute=self.config.get_int('notification_time_minute', 0)
        )

        retention_days = self.config.get_int('data_retention_days', -1)
        if retention_days >= 0:
            log.info(f"Deleting data older than {retention_days} days...")
            self.storage.delete_old_data(retention_days)
        else:
            log.info("Data retention disabled (keep forever)")

        log.info("RealTypeCoach started successfully!")

    def stop(self) -> None:
        """Stop all components."""
        log.info("Stopping RealTypeCoach...")

        self.running = False

        log.info("Stopping event handler...")
        self.event_handler.stop()

        log.info("Stopping layout monitor...")
        self.layout_monitor.stop()

        log.info("Stopping analyzer...")
        self.analyzer.stop()

        log.info("Stopping notification handler...")
        self.notification_handler.stop()

        log.info("RealTypeCoach stopped.")


def check_single_instance() -> bool:
    """Check if another instance is already running."""
    pid_file = Path.home() / '.local' / 'share' / 'realtypecoach' / 'realtypecoach.pid'

    if pid_file.exists():
        try:
            with open(pid_file, 'r') as f:
                pid = int(f.read().strip())
            try:
                os.kill(pid, 0)  # Check if process is alive
                print(f"Instance already running with PID {pid}")
                return False
            except ProcessLookupError:
                print("Stale PID file found, cleaning up...")
                pid_file.unlink()
        except (ValueError, IOError):
            pass

    return True


def main():
    """Main entry point."""
    # Check for single instance
    log.info("Starting RealTypeCoach...")
    if not check_single_instance():
        log.error("RealTypeCoach is already running. Exiting.")
        print("RealTypeCoach is already running. Exiting.")
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # Set default font to avoid malformed KDE font descriptions
    font = QFont()
    font.setFamily("Sans Serif")
    app.setFont(font)

    log.info("Creating Application instance...")
    application = Application()

    signal.signal(signal.SIGINT, lambda s, f: app.quit())
    signal.signal(signal.SIGTERM, lambda s, f: app.quit())

    # Create PID file
    pid_file = Path.home() / '.local' / 'share' / 'realtypecoach' / 'realtypecoach.pid'
    with open(pid_file, 'w') as f:
        f.write(str(os.getpid()))

    # Ensure PID file is cleaned up on exit
    import atexit
    def cleanup_pid():
        if pid_file.exists():
            pid_file.unlink()

    atexit.register(cleanup_pid)

    application.start()

    log.info("Starting Qt event loop...")
    ret = app.exec_()

    log.info(f"Qt event loop exited with code: {ret}")
    application.stop()

    # Clean up PID file
    cleanup_pid()

    log.info("RealTypeCoach shutdown complete")
    sys.exit(ret)


if __name__ == '__main__':
    main()
