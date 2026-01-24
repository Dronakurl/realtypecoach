#!/usr/bin/env python3
"""RealTypeCoach - KDE Wayland typing analysis application."""

import logging
import os
import signal
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from logging.handlers import RotatingFileHandler
from pathlib import Path
from queue import Empty, Queue

# Path constants (must be defined before logging setup)
DATA_DIR = Path.home() / ".local" / "share" / "realtypecoach"
XDG_STATE_HOME = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state")))
LOG_DIR = XDG_STATE_HOME / "realtypecoach"
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "realtypecoach"

# Setup logging with XDG state directory
LOG_DIR.mkdir(parents=True, exist_ok=True)
log_file = LOG_DIR / "realtypecoach.log"

# Configure rotating file handler (5MB max, keep 5 backups)
file_handler = RotatingFileHandler(
    log_file,
    maxBytes=5 * 1024 * 1024,  # 5MB
    backupCount=5,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[file_handler, logging.StreamHandler()],
)
log = logging.getLogger("realtypecoach")

import pyqtgraph as pg  # noqa: E402
from PySide6.QtCore import QObject, QTimer, Signal  # noqa: E402
from PySide6.QtGui import QFont, QIcon, QPainter, QPalette  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QDialog,
    QMessageBox,
    QPushButton,
)

from core.analyzer import Analyzer  # noqa: E402
from core.burst_config import BurstDetectorConfig  # noqa: E402
from core.burst_detector import BurstDetector  # noqa: E402
from core.dictionary_config import DictionaryConfig  # noqa: E402
from core.evdev_handler import EvdevHandler  # noqa: E402
from core.notification_handler import NotificationHandler  # noqa: E402
from core.storage import Storage  # noqa: E402
from core.sync_handler import SyncHandler  # noqa: E402
from ui.about_dialog import AboutDialog  # noqa: E402
from ui.settings_dialog import SettingsDialog  # noqa: E402
from ui.stats_panel import StatsPanel  # noqa: E402
from ui.tray_icon import TrayIcon  # noqa: E402
from utils.config import Config  # noqa: E402
from utils.crypto import CryptoManager  # noqa: E402
from utils.keyboard_detector import LayoutMonitor, get_current_layout  # noqa: E402


class Application(QObject):
    """Main application controller."""

    signal_update_stats = Signal(float, float, float, float)
    signal_update_slowest_keys = Signal(list)
    signal_update_fastest_keys = Signal(list)
    signal_update_hardest_words = Signal(list)
    signal_update_fastest_words_stats = Signal(list)
    signal_update_today_stats = Signal(int, int, float)
    signal_update_typing_time_display = Signal(float, float)
    signal_update_trend_data = Signal(list)
    signal_update_typing_time_graph = Signal(list)
    signal_update_worst_letter = Signal(str, float)
    signal_update_worst_word = Signal(object)
    signal_update_fastest_word = Signal(object)
    signal_update_keystrokes_bursts = Signal(int, int, int)
    signal_update_avg_burst_duration = Signal(int, int, int)
    signal_settings_changed = Signal(dict)
    signal_clipboard_words_ready = Signal(list)  # For clipboard copy operation
    signal_update_histogram_graph = Signal(list)  # For histogram data
    signal_update_recent_bursts = Signal(list)  # For recent bursts data

    def __init__(self) -> None:
        """Initialize application."""
        super().__init__()
        self.event_queue = Queue(maxsize=1000)
        self.running = False
        self._last_stats_update: int = 0
        self._last_activity_time: int = int(time.time())
        self._stats_update_timer: QTimer | None = None
        # Thread pool for background data fetching (limit to prevent thread leaks)
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="data_fetcher")
        # Thread-safe flag for stats panel visibility (avoid calling Qt methods from background threads)
        self._stats_panel_visible: bool = False

        self.init_data_directory()
        self.init_components()
        self.connect_signals()

    def init_data_directory(self) -> None:
        """Initialize data directory."""
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            log.error(f"Failed to create data directory: {e}")
            QMessageBox.critical(
                None, "Initialization Failed", f"Cannot create data directory:\n{e}"
            )
            sys.exit(1)

        self.db_path = DATA_DIR / "typing_data.db"
        self.icon_path = DATA_DIR / "icon.svg"
        self.icon_paused_path = DATA_DIR / "icon_paused.svg"
        self.icon_stopping_path = DATA_DIR / "icon_stopping.svg"

        try:
            from utils.icon_generator import save_icon

            save_icon(self.icon_path, active=True)
            save_icon(self.icon_paused_path, active=False)
            save_icon(self.icon_stopping_path, stopping=True)
        except Exception as e:
            log.error(f"Failed to generate icons: {e}")
            QMessageBox.critical(
                None,
                "Initialization Failed",
                f"Cannot generate application icons:\n{e}",
            )
            sys.exit(1)

        print(f"Data directory: {DATA_DIR}")
        print(f"Database: {self.db_path}")

        # Backup old unencrypted/undecryptable database if it exists
        if self.db_path.exists():
            import uuid

            import sqlcipher3 as sqlite3

            crypto = CryptoManager(self.db_path)

            # Check if database is actually encrypted
            is_encrypted = False
            if crypto.key_exists():
                try:
                    # Try to open with encryption
                    test_key = crypto.get_key()
                    conn = sqlite3.connect(self.db_path)
                    conn.execute(f"PRAGMA key = \"x'{test_key.hex()}'\"")
                    conn.execute("SELECT count(*) FROM sqlite_master")
                    conn.close()
                    is_encrypted = True
                except Exception:
                    # If opening with encryption fails, it's not an encrypted DB
                    is_encrypted = False

            # If database exists but cannot be decrypted, backup and create new
            if not is_encrypted:
                backup_path = self.db_path.with_suffix(f".db.{uuid.uuid4()}.backup")
                log.info(f"Old undecryptable database detected, backing up to {backup_path.name}")
                try:
                    self.db_path.rename(backup_path)
                    log.info(f"Backed up old database to {backup_path}")
                except Exception as e:
                    log.error(f"Failed to backup old database: {e}")
                    QMessageBox.critical(
                        None,
                        "Initialization Failed",
                        f"Failed to backup old database:\n{e}",
                    )
                    sys.exit(1)

    def init_components(self) -> None:
        """Initialize all components."""
        try:
            self.config = Config(self.db_path)
        except RuntimeError as e:
            if "keyring" in str(e).lower():
                QMessageBox.critical(
                    None,
                    "Keyring Not Available",
                    f"{e}\n\nA system keyring is required to encrypt your typing data securely.",
                )
                sys.exit(1)
            raise

        # Build dictionary configuration
        enabled_languages = self.config.get_list("enabled_languages")
        enabled_dictionaries = self.config.get("enabled_dictionaries", "")
        enabled_dictionary_paths = enabled_dictionaries.split(",") if enabled_dictionaries else []
        accept_all_mode = self.config.get("dictionary_mode") == "accept_all"

        dictionary_config = DictionaryConfig(
            enabled_languages=enabled_languages,
            enabled_dictionary_paths=enabled_dictionary_paths,
            accept_all_mode=accept_all_mode,
        )

        self.storage = Storage(
            self.db_path,
            word_boundary_timeout_ms=self.config.get_int("word_boundary_timeout_ms", 1000),
            dictionary_config=dictionary_config,
            config=self.config,
            ignore_file_path=CONFIG_DIR / "ignorewords.txt",
        )

        # Clean ignored words from database
        deleted_count = self.storage.clean_ignored_words()
        if deleted_count > 0:
            log.info(f"Cleaned {deleted_count} ignored word entries from database")

        current_layout = get_current_layout()
        print(f"Detected keyboard layout: {current_layout}")

        burst_config = BurstDetectorConfig(
            burst_timeout_ms=self.config.get_int("burst_timeout_ms", 1000),
            high_score_min_duration_ms=self.config.get_int("high_score_min_duration_ms", 5000),
            duration_calculation_method=self.config.get("burst_duration_calculation", "total_time"),
            active_time_threshold_ms=self.config.get_int("active_time_threshold_ms", 500),
            min_key_count=self.config.get_int("min_burst_key_count", 10),
            min_duration_ms=self.config.get_int("min_burst_duration_ms", 5000),
        )

        self.burst_detector = BurstDetector(
            config=burst_config,
            on_burst_complete=self.on_burst_complete,
        )

        self.event_handler = EvdevHandler(
            event_queue=self.event_queue,
            layout_getter=self.get_current_layout,
            stats_panel_visible_getter=lambda: self._stats_panel_visible,
        )

        self.analyzer = Analyzer(self.storage)

        self.notification_handler = NotificationHandler(
            summary_getter=self.analyzer.get_daily_summary,
            storage=self.storage,
            min_burst_ms=self.config.get_int("notification_min_burst_ms", 10000),
            threshold_days=self.config.get_int("notification_threshold_days", 30),
            threshold_update_sec=self.config.get_int("notification_threshold_update_sec", 300),
        )

        self.layout_monitor = LayoutMonitor(callback=self.on_layout_changed, poll_interval=60)

        # Initialize sync handler
        auto_sync_enabled = self.config.get_bool("auto_sync_enabled", False)
        auto_sync_interval = self.config.get_int("auto_sync_interval_sec", 300)
        self.sync_handler = SyncHandler(
            storage=self.storage,
            config=self.config,
            enabled=auto_sync_enabled,
            interval_sec=auto_sync_interval,
        )

        self.stats_panel = StatsPanel(icon_path=str(self.icon_path))
        self.tray_icon = TrayIcon(
            self.stats_panel,
            self.icon_path,
            self.icon_paused_path,
            self.icon_stopping_path,
        )

    def connect_signals(self) -> None:
        """Connect all signals."""
        # Use Qt.QueuedConnection to ensure signals cross thread boundaries properly
        from PySide6.QtCore import Qt

        self.signal_update_stats.connect(
            self.stats_panel.update_wpm,
            Qt.ConnectionType.QueuedConnection,
        )
        self.signal_update_slowest_keys.connect(
            self.stats_panel.update_slowest_keys,
            Qt.ConnectionType.QueuedConnection,
        )
        self.signal_update_fastest_keys.connect(
            self.stats_panel.update_fastest_keys,
            Qt.ConnectionType.QueuedConnection,
        )
        self.signal_update_hardest_words.connect(
            self.stats_panel.update_hardest_words,
            Qt.ConnectionType.QueuedConnection,
        )
        self.signal_update_fastest_words_stats.connect(
            self.stats_panel.update_fastest_words,
            Qt.ConnectionType.QueuedConnection,
        )
        self.signal_update_typing_time_display.connect(
            self.stats_panel.update_typing_time_display,
            Qt.ConnectionType.QueuedConnection,
        )
        self.signal_update_worst_word.connect(
            self.stats_panel.update_worst_word,
            Qt.ConnectionType.QueuedConnection,
        )
        self.signal_update_fastest_word.connect(
            self.stats_panel.update_fastest_word,
            Qt.ConnectionType.QueuedConnection,
        )
        self.signal_update_keystrokes_bursts.connect(
            self.stats_panel.update_keystrokes_bursts,
            Qt.ConnectionType.QueuedConnection,
        )
        self.signal_update_avg_burst_duration.connect(
            self.stats_panel.update_avg_burst_duration,
            Qt.ConnectionType.QueuedConnection,
        )
        self.signal_update_trend_data.connect(
            self.stats_panel.update_trend_graph,
            Qt.ConnectionType.QueuedConnection,
        )
        self.signal_update_typing_time_graph.connect(
            self.stats_panel.update_typing_time_graph,
            Qt.ConnectionType.QueuedConnection,
        )
        self.signal_update_histogram_graph.connect(
            self.stats_panel.update_histogram_graph,
            Qt.ConnectionType.QueuedConnection,
        )
        self.signal_update_recent_bursts.connect(
            self.stats_panel.update_recent_bursts,
            Qt.ConnectionType.QueuedConnection,
        )

        self.notification_handler.signal_daily_summary.connect(self.show_daily_notification)
        self.notification_handler.signal_exceptional_burst.connect(
            self.show_exceptional_notification
        )
        self.notification_handler.signal_worst_letter_changed.connect(
            self.show_worst_letter_notification
        )
        self.signal_update_worst_letter.connect(
            self.stats_panel.update_worst_letter,
            Qt.ConnectionType.QueuedConnection,
        )

        self.tray_icon.settings_changed.connect(self.apply_settings)
        self.tray_icon.settings_requested.connect(self.show_settings_dialog)
        self.tray_icon.stats_requested.connect(self.update_statistics)
        self.tray_icon.about_requested.connect(self.show_about_dialog)
        self.stats_panel.settings_requested.connect(self.show_settings_dialog)

        self.stats_panel.set_trend_data_callback(self.provide_trend_data)
        self.stats_panel.set_typing_time_data_callback(self.provide_typing_time_data)
        self.stats_panel.set_histogram_data_callback(self.provide_histogram_data)
        self.stats_panel.set_words_clipboard_callback(self.fetch_words_for_clipboard)

        self.signal_clipboard_words_ready.connect(
            self.stats_panel._on_clipboard_words_ready,
            Qt.ConnectionType.QueuedConnection,
        )

        # Connect stats panel visibility signal to update thread-safe flag
        self.stats_panel.visibility_changed.connect(self._on_stats_panel_visibility_changed)

        # Connect sync handler signals
        self.sync_handler.signal_sync_failed.connect(self._on_sync_failed)

    def get_current_layout(self) -> str:
        """Get current keyboard layout."""
        layout = self.config.get("keyboard_layout", "auto")
        if layout == "auto":
            return get_current_layout()
        return layout

    def _on_stats_panel_visibility_changed(self, visible: bool) -> None:
        """Handle stats panel visibility changes.

        Updates the thread-safe flag used by background threads to avoid
        calling Qt methods from non-GUI threads.

        Args:
            visible: True if panel is now visible, False if hidden
        """
        self._stats_panel_visible = visible

    def on_burst_complete(self, burst) -> None:
        """Handle burst completion."""
        self.analyzer.process_burst(burst)

        # Update statistics with debouncing when a burst completes, but only if panel is visible
        is_visible = self.stats_panel.isVisible()
        log.info(
            f"Burst complete: {burst.key_count} keys, {burst.duration_ms / 1000:.1f}s, panel visible: {is_visible}"
        )
        if is_visible:
            self._schedule_stats_update()

        # Update recent bursts display immediately (lightweight query)
        try:
            recent_bursts = self.storage.get_recent_bursts(limit=3)
            self.signal_update_recent_bursts.emit(recent_bursts)
        except Exception as e:
            log.warning(f"Failed to update recent bursts: {e}")

        if burst.qualifies_for_high_score:
            wpm = self._calculate_wpm(burst.net_key_count, burst.duration_ms)
            self.notification_handler.notify_exceptional_burst(
                wpm, burst.net_key_count, burst.duration_ms, burst.backspace_ratio
            )

    def on_layout_changed(self, new_layout: str) -> None:
        """Handle keyboard layout change."""
        print(f"Keyboard layout changed to: {new_layout}")
        self.tray_icon.show_notification(
            "Keyboard Layout Changed", f"New layout: {new_layout}", "info"
        )

    def _schedule_stats_update(self) -> None:
        """Schedule statistics update with debouncing.

        Ensures that statistics updates are debounced to prevent excessive
        database queries when multiple bursts complete in quick succession.
        """
        if self._stats_update_timer is not None:
            # Cancel pending update
            self._stats_update_timer.stop()

        # Create timer if it doesn't exist
        if self._stats_update_timer is None:
            self._stats_update_timer = QTimer()
            self._stats_update_timer.setSingleShot(True)
            self._stats_update_timer.timeout.connect(self.update_statistics)

        # Schedule update in 500ms
        self._stats_update_timer.start(500)

    def _calculate_wpm(self, key_count: int, duration_ms: int) -> float:
        """Calculate words per minute.

        Note: key_count should already be net_key_count (with backspaces subtracted).
        """
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
        if not self.tray_icon.monitoring_active:
            return
        self.tray_icon.show_notification(summary.title, summary.message, "info")

    def show_exceptional_notification(self, wpm: float) -> None:
        """Show exceptional burst notification."""
        if not self.tray_icon.monitoring_active:
            return
        self.tray_icon.show_notification(
            "🚀 Exceptional Typing Speed!",
            f"{wpm:.1f} WPM - Top 95% burst!",
            "info",
        )

    def show_worst_letter_notification(self, change) -> None:
        """Show worst letter change notification.

        Args:
            change: WorstLetterChange pydantic model
        """
        if not self.tray_icon.monitoring_active:
            return

        if change.improvement:
            message = (
                f"Previous worst: '{change.previous_key}' ({change.previous_time_ms:.0f}ms)\n"
                f"New worst: '{change.new_key}' ({change.new_time_ms:.0f}ms)\n"
                f"Great progress!"
            )
            icon_type = "info"
        else:
            message = (
                f"Previous worst: '{change.previous_key}' ({change.previous_time_ms:.0f}ms)\n"
                f"New worst: '{change.new_key}' ({change.new_time_ms:.0f}ms)\n"
                f"Focus on this key!"
            )
            icon_type = "warning"

        self.tray_icon.show_notification("🔤 Hardest Letter Changed", message, icon_type)

    def _on_sync_failed(self, error: str) -> None:
        """Handle sync failure.

        Args:
            error: Error message
        """
        log.warning(f"Background sync failed: {error}")
        # Optionally show tray notification for persistent failures
        # self.tray_icon.show_notification(
        #     "Sync Failed", f"Background sync failed: {error}", "warning"
        # )

    def apply_settings(self, new_settings: dict) -> None:
        """Apply new settings."""
        # Special keys that should not be saved to config
        special_keys = {"__clear_database__", "export_csv_path"}

        if "enabled_dictionaries" in new_settings:
            log.info(f"Saving enabled_dictionaries: {new_settings['enabled_dictionaries']!r}")

        for key, value in new_settings.items():
            if key not in special_keys:
                self.config.set(key, value)

        # Reload dictionary configuration if language settings changed
        if (
            "dictionary_mode" in new_settings
            or "enabled_languages" in new_settings
            or "enabled_dictionaries" in new_settings
        ):
            log.info("Dictionary configuration changed, storage will reload on next restart")

        # Update worst letter notification settings
        if "worst_letter_notifications_enabled" in new_settings:
            self.notification_handler.worst_letter_notifications_enabled = self.config.get_bool(
                "worst_letter_notifications_enabled", False
            )
        if "worst_letter_notification_debounce_min" in new_settings:
            debounce_min = self.config.get_int("worst_letter_notification_debounce_min", 5)
            self.analyzer.worst_letter_debounce_ms = debounce_min * 60 * 1000

        # Update daily summary settings
        if "daily_summary_enabled" in new_settings:
            self.notification_handler.daily_summary_enabled = self.config.get_bool(
                "daily_summary_enabled", True
            )

        # Update auto-sync settings
        if "auto_sync_enabled" in new_settings or "auto_sync_interval_sec" in new_settings:
            auto_sync_enabled = self.config.get_bool("auto_sync_enabled", False)
            auto_sync_interval = self.config.get_int("auto_sync_interval_sec", 300)
            self.sync_handler.update_settings(auto_sync_enabled, auto_sync_interval)

        if "__clear_database__" in new_settings:
            self.storage.clear_database()
            # Refresh statistics panel with empty data
            self.signal_update_stats.emit(0, 0, 0, 0)
            self.signal_update_slowest_keys.emit([])
            self.signal_update_fastest_keys.emit([])
            self.signal_update_hardest_words.emit([])
            self.signal_update_fastest_words_stats.emit([])
            self.signal_update_keystrokes_bursts.emit(0, 0, 0)
            self.signal_update_typing_time_display.emit(0, 0)
            self.signal_update_trend_data.emit([])
            self.signal_update_typing_time_graph.emit([])
            self.signal_update_histogram_graph.emit([])
            self.signal_update_worst_letter.emit("", 0.0)
            self.signal_update_worst_word.emit(None)
            msg_box = QMessageBox(
                QMessageBox.Information,
                "Data Cleared",
                "All typing data has been deleted.",
                QMessageBox.Ok,
                None,
            )
            msg_box.setStyleSheet(
                """
                QMessageBox { messagebox-text-interaction-flags: 5; }
                QPushButton {
                    color: palette(text);
                }
            """
            )
            for button in msg_box.findChildren(QPushButton):
                icon = button.icon()
                if not icon.isNull():
                    pixmap = icon.pixmap(button.iconSize())
                    painter = QPainter(pixmap)
                    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
                    painter.fillRect(pixmap.rect(), button.palette().color(QPalette.ButtonText))
                    painter.end()
                    button.setIcon(QIcon(pixmap))
            msg_box.exec()

        if "export_csv_path" in new_settings:
            try:
                from datetime import datetime

                default_date = datetime.now().strftime("%Y-%m-%d")
                count = self.storage.export_to_csv(
                    Path(new_settings["export_csv_path"]), start_date=default_date
                )
                QMessageBox.information(
                    None, "Export Complete", f"Exported {count:,} events to CSV."
                )
            except Exception as e:
                QMessageBox.critical(None, "Export Failed", f"Failed to export data: {e}")

    def provide_trend_data(self, smoothness: int) -> None:
        """Provide trend data to stats panel.

        Args:
            smoothness: Smoothing level (1-100)
        """

        def fetch_data():
            try:
                data = self.analyzer.get_wpm_burst_sequence(smoothness=smoothness)
                self.signal_update_trend_data.emit(data)
            except Exception as e:
                log.error(f"Error fetching trend data: {e}")

        # Submit to thread pool to limit concurrent background threads
        self._executor.submit(fetch_data)

    def provide_typing_time_data(self, granularity: str) -> None:
        """Provide typing time data to stats panel.

        Args:
            granularity: Time granularity ("day", "week", "month", "quarter")
        """

        def fetch_data():
            try:
                log.info(f"Fetching typing time data with granularity: {granularity}")
                data = self.analyzer.get_typing_time_data(granularity=granularity)
                log.info(f"Got {len(data)} data points, emitting signal")
                self.signal_update_typing_time_graph.emit(data)
                log.info("Signal emitted successfully")
            except Exception as e:
                log.error(f"Error fetching typing time data: {e}")

        # Submit to thread pool to limit concurrent background threads
        self._executor.submit(fetch_data)

    def provide_histogram_data(self, bin_count: int) -> None:
        """Provide histogram data to stats panel.

        Args:
            bin_count: Number of histogram bins
        """

        def fetch_data():
            try:
                log.info(f"Fetching histogram data with {bin_count} bins")
                data = self.analyzer.get_burst_wpm_histogram(bin_count=bin_count)
                log.info(f"Got {len(data)} bins, emitting signal")
                self.signal_update_histogram_graph.emit(data)
                log.info("Histogram signal emitted successfully")
            except Exception as e:
                log.error(f"Error fetching histogram data: {e}")

        # Submit to thread pool to limit concurrent background threads
        self._executor.submit(fetch_data)

    def fetch_words_for_clipboard(self, count: int) -> None:
        """Fetch slowest words in background thread and emit signal.

        Args:
            count: Number of words to fetch
        """

        def fetch_in_thread():
            try:
                words = self.analyzer.get_slowest_words(
                    limit=count, layout=self.get_current_layout()
                )
                # Emit signal to main thread
                self.signal_clipboard_words_ready.emit(words)
            except Exception as e:
                log.error(f"Error fetching words for clipboard: {e}")
                self.signal_clipboard_words_ready.emit([])

        # Submit to thread pool to limit concurrent background threads
        self._executor.submit(fetch_in_thread)

    def process_event_queue(self) -> None:
        """Process events from queue."""
        # Process all available events at once (non-blocking)
        processed_count = 0
        logged = False
        while processed_count < 1000:  # Increased limit to handle fast typing
            try:
                key_event = self.event_queue.get_nowait()

                # Log first few processed events for debugging (sanitize key_name to prevent logging sensitive data)
                if not logged and processed_count < 3:
                    # Don't log actual letter/number characters - just log the type of key
                    if len(key_event.key_name) == 1:
                        key_type = (
                            "CHARACTER" if key_event.key_name.isalnum() else key_event.key_name
                        )
                    else:
                        key_type = (
                            key_event.key_name
                        )  # Special keys like SPACE, ENTER are safe to log
                    log.info(f"Processing key event: {key_type}")
                    logged = True

                # Detect if key is backspace
                is_backspace = key_event.key_name == "BACKSPACE"
                self.burst_detector.process_key_event(key_event.timestamp_ms, True, is_backspace)

                self.analyzer.process_key_event(
                    key_event.keycode,
                    key_event.key_name,
                    key_event.timestamp_ms,
                    self.get_current_layout(),
                )

                processed_count += 1

            except Empty:
                break  # Queue empty

        # Only update stats panel if it's visible (avoid wasting resources when hidden)
        if self.stats_panel.isVisible():
            current_time = int(time.time())

            # Update activity time when processing events
            if processed_count > 0:
                self._last_activity_time = current_time

            # Use adaptive interval based on typing activity
            idle_threshold = self.config.get_int("idle_threshold_sec", 10)
            idle_time = current_time - self._last_activity_time

            if idle_time >= idle_threshold:
                # Idle - use slower update interval
                stats_interval = self.config.get_int("stats_update_interval_idle_sec", 15)
            else:
                # Active or recently active - use normal update interval
                stats_interval = self.config.get_int("stats_update_interval_active_sec", 5)

            if current_time - self._last_stats_update >= stats_interval:
                self.update_statistics()
                self._last_stats_update = current_time

        # Adaptively adjust event queue polling interval based on activity
        # This reduces CPU usage when the user is not actively typing
        current_time = time.time()
        idle_time = current_time - self._last_activity_time

        if idle_time > 30:
            # Long idle - check every 5 seconds
            new_interval = 5000
        elif idle_time > 5:
            # Recently active - check every 2 seconds
            new_interval = 2000
        else:
            # Active typing - check every 500ms
            new_interval = 500

        # Only update if interval changed
        if self.process_queue_timer.interval() != new_interval:
            log.debug(f"Adjusting queue poll interval to {new_interval}ms (idle: {idle_time:.1f}s)")
            self.process_queue_timer.setInterval(new_interval)

    def update_statistics(self) -> None:
        """Update statistics display."""
        log.info("update_statistics() called")

        stats = self.analyzer.get_statistics()
        long_term_avg = self.analyzer.get_long_term_average_wpm() or 0
        all_time_best = self.analyzer.get_all_time_high_score() or 0

        log.info(
            f"Emitting stats signal: burst_wpm={stats['burst_wpm']:.1f}, today_best={stats['personal_best_today'] or 0:.1f}"
        )
        self.signal_update_stats.emit(
            stats["burst_wpm"],
            stats["personal_best_today"] or 0,
            long_term_avg,
            all_time_best,
        )

        slowest_keys = self.analyzer.get_slowest_keys(
            limit=10,
            layout=self.get_current_layout(),
        )
        self.signal_update_slowest_keys.emit(slowest_keys)

        fastest_keys = self.analyzer.get_fastest_keys(
            limit=10,
            layout=self.get_current_layout(),
        )
        self.signal_update_fastest_keys.emit(fastest_keys)

        hardest_words = self.analyzer.get_slowest_words(limit=10, layout=self.get_current_layout())
        self.signal_update_hardest_words.emit(hardest_words)

        fastest_words = self.analyzer.get_fastest_words(limit=10, layout=self.get_current_layout())
        self.signal_update_fastest_words_stats.emit(fastest_words)

        # Update typing time display (today + all-time excluding today)
        all_time_typing_sec = self.storage.get_all_time_typing_time(
            exclude_today=stats["date"]
        ) + int(stats["total_typing_sec"])
        self.signal_update_typing_time_display.emit(stats["total_typing_sec"], all_time_typing_sec)

        # Get worst letter and update display (reuse slowest_keys from above)
        if slowest_keys:
            worst = slowest_keys[0]
            self.signal_update_worst_letter.emit(worst.key_name, worst.avg_press_time)

            # Check for worst letter change
            change = self.analyzer._check_worst_letter_change()
            if change:
                self.notification_handler.check_and_notify_worst_letter_change(change)

        # Get worst word and update display (reuse hardest_words from above)
        if hardest_words:
            worst_word = hardest_words[0]
            self.signal_update_worst_word.emit(worst_word)

        # Get fastest word and update display (reuse fastest_words from above)
        if fastest_words:
            fastest_word = fastest_words[0]
            self.signal_update_fastest_word.emit(fastest_word)

        # Update all-time keystrokes and bursts (database excluding today + today's in-memory stats)
        db_keystrokes, db_bursts = self.storage.get_all_time_keystrokes_and_bursts(
            exclude_today=stats["date"]
        )
        all_time_keystrokes = db_keystrokes + stats["total_keystrokes"]
        all_time_bursts = db_bursts + stats["total_bursts"]
        today_keystrokes = stats["total_keystrokes"]
        self.signal_update_keystrokes_bursts.emit(
            all_time_keystrokes, all_time_bursts, today_keystrokes
        )

        # Update average burst duration stats
        avg_ms, min_ms, max_ms = self.storage.get_burst_duration_stats_ms()
        self.signal_update_avg_burst_duration.emit(avg_ms, min_ms, max_ms)

    def show_settings_dialog(self) -> None:
        """Show settings dialog."""
        enabled_dicts_value = self.config.get("enabled_dictionaries", "")
        log.info(
            f"show_settings_dialog: loaded enabled_dictionaries from config: {enabled_dicts_value!r}"
        )
        current_settings = {
            "burst_timeout_ms": self.config.get_int("burst_timeout_ms", 1000),
            "burst_duration_calculation": self.config.get(
                "burst_duration_calculation", "total_time"
            ),
            "active_time_threshold_ms": self.config.get_int("active_time_threshold_ms", 500),
            "high_score_min_duration_ms": self.config.get_int("high_score_min_duration_ms", 5000),
            "keyboard_layout": self.config.get("keyboard_layout", "auto"),
            "notification_time_hour": self.config.get_int("notification_time_hour", 18),
            "worst_letter_notifications_enabled": self.config.get_bool(
                "worst_letter_notifications_enabled", False
            ),
            "worst_letter_notification_debounce_min": self.config.get_int(
                "worst_letter_notification_debounce_min", 5
            ),
            "data_retention_days": self.config.get_int("data_retention_days", -1),
            "dictionary_mode": self.config.get("dictionary_mode", "validate"),
            "enabled_languages": self.config.get("enabled_languages", "en,de"),
            "enabled_dictionaries": enabled_dicts_value,
            # Database settings
            "postgres_sync_enabled": self.config.get_bool("postgres_sync_enabled", False),
            "postgres_host": self.config.get("postgres_host", ""),
            "postgres_port": self.config.get_int("postgres_port", 5432),
            "postgres_database": self.config.get("postgres_database", "realtypecoach"),
            "postgres_user": self.config.get("postgres_user", ""),
            "postgres_sslmode": self.config.get("postgres_sslmode", "require"),
            # Auto-sync settings
            "auto_sync_enabled": self.config.get_bool("auto_sync_enabled", False),
            "auto_sync_interval_sec": self.config.get_int("auto_sync_interval_sec", 300),
        }
        dialog = SettingsDialog(
            current_settings, storage=self.storage, sync_handler=self.sync_handler
        )
        if dialog.exec() == QDialog.Accepted:
            # Use dialog.settings if it was set by clear_data/export_csv, otherwise get fresh settings
            if dialog.settings:
                new_settings = dialog.settings
            else:
                new_settings = dialog.get_settings()
            self.apply_settings(new_settings)

    def show_about_dialog(self) -> None:
        """Show about dialog."""
        dialog = AboutDialog()
        dialog.exec()

    def start(self) -> None:
        """Start all components."""
        log.info("Starting RealTypeCoach...")

        self.running = True

        log.info("Starting event handler...")
        try:
            self.event_handler.start()
        except RuntimeError as e:
            error_msg = str(e)
            if "input" in error_msg.lower() and "group" in error_msg.lower():
                QMessageBox.critical(
                    None,
                    "RealTypeCoach - Permission Error",
                    "RealTypeCoach requires access to keyboard devices.\n\n"
                    "You need to be in the 'input' group:\n"
                    "  sudo usermod -aG input $USER\n\n"
                    "Then log out and log back in for the changes to take effect.",
                )
                log.error(f"Input group missing: {error_msg}")
                sys.exit(1)
            else:
                raise

        log.info("Starting layout monitor...")
        self.layout_monitor.start()

        log.info("Starting analyzer...")
        self.analyzer.start()

        # Load and display existing statistics (only if panel is visible)
        if self.stats_panel.isVisible():
            self.update_statistics()

        log.info("Starting notification handler...")
        self.notification_handler.start()

        # Start sync handler if enabled
        if self.sync_handler.enabled:
            log.info("Starting sync handler...")
            self.sync_handler.start()

        self.process_queue_timer = QTimer()
        self.process_queue_timer.timeout.connect(self.process_event_queue)
        self.process_queue_timer.start(500)  # Check every 500ms

        self.tray_icon.show()

        self.notification_handler.set_notification_time(
            hour=self.config.get_int("notification_time_hour", 18),
            minute=0,
        )

        retention_days = self.config.get_int("data_retention_days", -1)
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

        log.info("Stopping sync handler...")
        self.sync_handler.stop()

        log.info("Closing storage connection pool...")
        self.storage.close()

        log.info("Shutting down thread pool...")
        self._executor.shutdown(wait=True)

        log.info("RealTypeCoach stopped.")


def check_single_instance() -> bool:
    """Check if another instance is already running and terminate it."""
    pid_file = DATA_DIR / "realtypecoach.pid"

    if pid_file.exists():
        try:
            with open(pid_file) as f:
                pid = int(f.read().strip())
            try:
                os.kill(pid, 0)  # Check if process is alive
                print(f"Instance already running with PID {pid}, terminating...")

                # Send SIGTERM for graceful shutdown
                os.kill(pid, signal.SIGTERM)

                # Wait for process to terminate (max 5 seconds)
                for _ in range(50):
                    try:
                        os.kill(pid, 0)
                        time.sleep(0.1)
                    except ProcessLookupError:
                        print(f"Instance {pid} terminated successfully")
                        break
                else:
                    # Process didn't terminate gracefully, force kill
                    print(f"Instance {pid} did not terminate gracefully, forcing...")
                    os.kill(pid, signal.SIGKILL)
                    time.sleep(0.5)

                # Clean up stale PID file
                if pid_file.exists():
                    pid_file.unlink()

            except ProcessLookupError:
                print("Stale PID file found, cleaning up...")
                pid_file.unlink()
        except (OSError, ValueError):
            pass

    return True


def main():
    """Main entry point."""
    log.info("Starting RealTypeCoach...")
    check_single_instance()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("RealTypeCoach")
    app.setApplicationDisplayName("RealTypeCoach")

    # Configure PyQtGraph to use Qt theme colors
    palette = app.palette()
    bg_color = palette.color(QPalette.ColorRole.Window)
    fg_color = palette.color(QPalette.ColorRole.WindowText)
    pg.setConfigOption("background", bg_color)
    pg.setConfigOption("foreground", fg_color)
    pg.setConfigOptions(antialias=True)

    # Set default font to avoid malformed KDE font descriptions
    font = QFont()
    font.setFamily("Sans Serif")
    app.setFont(font)

    log.info("Creating Application instance...")
    application = Application()

    # Set application icon
    app.setWindowIcon(QIcon(str(application.icon_path)))

    signal.signal(signal.SIGINT, lambda s, f: app.quit())
    signal.signal(signal.SIGTERM, lambda s, f: app.quit())

    # Create PID file
    pid_file = DATA_DIR / "realtypecoach.pid"
    with open(pid_file, "w") as f:
        f.write(str(os.getpid()))

    # Ensure PID file is cleaned up on exit
    import atexit

    def cleanup_pid():
        if pid_file.exists():
            pid_file.unlink()

    atexit.register(cleanup_pid)

    application.start()

    log.info("Starting Qt event loop...")
    ret = app.exec()

    log.info(f"Qt event loop exited with code: {ret}")
    application.stop()

    # Clean up PID file
    cleanup_pid()

    log.info("RealTypeCoach shutdown complete")
    sys.exit(ret)


if __name__ == "__main__":
    main()
