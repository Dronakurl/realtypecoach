#!/usr/bin/env python3
"""RealTypeCoach - Wayland typing analysis application."""

import logging
import os
import re
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

# Detect if running from installed location or development
# Installed: ~/.local/share/realtypecoach/main.py → INFO
# Development: running from source directory → DEBUG
script_path = Path(__file__).resolve()
is_installed = script_path == (DATA_DIR / "main.py")
log_level = logging.INFO if is_installed else logging.DEBUG

logging.basicConfig(
    level=log_level,
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
from core.ollama_client import OllamaClient  # noqa: E402
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

    signal_update_stats = Signal(float, float, float, float, float)
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
    signal_update_avg_burst_duration = Signal(int, int, int, int, float)
    signal_settings_changed = Signal(dict)
    signal_clipboard_words_ready = Signal(list)  # For clipboard copy operation
    signal_update_histogram_graph = Signal(list)  # For histogram data
    signal_update_recent_bursts = Signal(list)  # For recent bursts data
    signal_update_digraph_stats = Signal(list, list)  # For digraph statistics (fastest, slowest)
    signal_text_generated = Signal(str)  # For Ollama text generation
    signal_text_generation_failed = Signal(str)  # For Ollama errors
    signal_ollama_available = Signal(bool)  # Ollama availability status

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
        exclude_names_enabled = self.config.get_bool("exclude_names_enabled", False)

        dictionary_config = DictionaryConfig(
            enabled_languages=enabled_languages,
            enabled_dictionary_paths=enabled_dictionary_paths,
            accept_all_mode=accept_all_mode,
            exclude_names_enabled=exclude_names_enabled,
        )

        self.storage = Storage(
            self.db_path,
            word_boundary_timeout_ms=self.config.get_int("word_boundary_timeout_ms", 1000),
            dictionary_config=dictionary_config,
            config=self.config,
            ignore_file_path=CONFIG_DIR / "ignorewords.txt",
        )

        # Initialize default LLM prompts if needed
        self.storage.initialize_default_prompts()

        # Clean ignored words from database
        deleted_count = self.storage.clean_ignored_words()
        if deleted_count > 0:
            log.info(f"Cleaned {deleted_count} ignored word entries from database")

        # Clean common names from database (if exclude_names is enabled)
        if exclude_names_enabled:
            deleted_names = self.storage.delete_all_names_from_database()
            if deleted_names > 0:
                log.info(f"Cleaned {deleted_names} common name entries from database")

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

        # Initialize Ollama client with model from config
        model = self.config.get("llm_model", "gemma2:2b")
        self.ollama_client = OllamaClient(model=model)

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
        self.signal_update_digraph_stats.connect(
            self.stats_panel.update_digraph_stats,
            Qt.ConnectionType.QueuedConnection,
        )

        self.notification_handler.signal_daily_summary.connect(self.show_daily_notification)
        self.notification_handler.signal_exceptional_burst.connect(
            self.show_exceptional_notification
        )
        self.notification_handler.signal_worst_letter_changed.connect(
            self.show_worst_letter_notification
        )
        self.notification_handler.signal_unrealistic_burst.connect(
            self.show_unrealistic_speed_notification
        )
        self.signal_update_worst_letter.connect(
            self.stats_panel.update_worst_letter,
            Qt.ConnectionType.QueuedConnection,
        )

        self.tray_icon.settings_changed.connect(self.apply_settings)
        self.tray_icon.settings_requested.connect(self.show_settings_dialog)
        self.tray_icon.stats_requested.connect(self.update_statistics)
        self.tray_icon.about_requested.connect(self.show_about_dialog)
        self.tray_icon.practice_requested.connect(self.practice_hardest_words)
        self.stats_panel.settings_requested.connect(self.show_settings_dialog)

        self.stats_panel.set_trend_data_callback(self.provide_trend_data)
        self.stats_panel.set_typing_time_data_callback(self.provide_typing_time_data)
        self.stats_panel.set_histogram_data_callback(self.provide_histogram_data)
        self.stats_panel.set_words_clipboard_callback(self.fetch_words_for_clipboard)
        self.stats_panel.set_digraph_data_callback(self.provide_digraph_data)
        self.stats_panel.set_text_generation_callback(self.generate_text_with_ollama)

        self.signal_clipboard_words_ready.connect(
            self.stats_panel._on_clipboard_words_ready,
            Qt.ConnectionType.QueuedConnection,
        )

        # Connect Ollama text generation signals
        self.ollama_client.signal_generation_complete.connect(
            self.stats_panel.on_text_generated,
            Qt.ConnectionType.QueuedConnection,
        )

        self.ollama_client.signal_generation_failed.connect(
            self.stats_panel.on_text_generation_failed,
            Qt.ConnectionType.QueuedConnection,
        )

        self.signal_ollama_available.connect(
            self.stats_panel.set_ollama_available,
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
        # Pre-check for unrealistic WPM before processing
        max_wpm_threshold = self.config.get_int("max_realistic_wpm", 300)
        if burst.key_count > 0:
            # Calculate WPM for validation
            # Net keystrokes = total - 2*backspaces
            net_keystrokes = max(0, burst.key_count - (burst.backspace_count * 2))
            burst_wpm = self._calculate_wpm(net_keystrokes, burst.duration_ms)

            if burst_wpm > max_wpm_threshold:
                log.warning(
                    f"Unrealistic burst detected: {burst_wpm:.1f} WPM > {max_wpm_threshold} WPM threshold, "
                    f"{burst.key_count} keys, {burst.duration_ms / 1000:.1f}s"
                )
                # Emit signal for notification
                self.notification_handler.signal_unrealistic_burst.emit(burst_wpm, burst.key_count)
                # Return early - no processing, no storage
                return

        self.analyzer.process_burst(burst, max_wpm_threshold=max_wpm_threshold)

        # Update statistics with debouncing when a burst completes, but only if panel is visible
        log.info(
            f"Burst complete: {burst.key_count} keys, {burst.duration_ms / 1000:.1f}s, "
            f"panel visible: {self._stats_panel_visible}"
        )
        if self._stats_panel_visible:
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

    def show_unrealistic_speed_notification(self, wpm: float, key_count: int) -> None:
        """Show notification for unrealistic typing speed.

        Args:
            wpm: Words per minute detected
            key_count: Number of keystrokes in the burst
        """
        if not self.config.get_bool("unrealistic_speed_warning_enabled", True):
            return

        threshold = self.config.get_int("max_realistic_wpm", 300)

        self.tray_icon.show_notification(
            "⚠️ Unrealistic Typing Speed Detected",
            f"{wpm:.1f} WPM detected (threshold: {threshold} WPM).\n"
            f"This burst was not recorded to prevent data corruption.\n"
            f"Burst: {key_count} keystrokes",
            "warning",
        )

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

        # Log postgres_sync_enabled for debugging
        if "postgres_sync_enabled" in new_settings:
            log.info(
                f"apply_settings: postgres_sync_enabled = {new_settings['postgres_sync_enabled']!r} "
                f"(type: {type(new_settings['postgres_sync_enabled']).__name__})"
            )

        # Track old exclude_names_enabled value before applying changes
        old_exclude_names = self.config.get_bool("exclude_names_enabled", False)

        for key, value in new_settings.items():
            if key not in special_keys:
                self.config.set(key, value)

        # Save exclude_names_enabled to database settings table for sync
        if "exclude_names_enabled" in new_settings:
            new_value = self.config.get_bool("exclude_names_enabled", False)
            # Save to database for sync
            try:
                self.storage.adapter.upsert_setting("exclude_names_enabled", str(new_value))
                log.info(f"Saved exclude_names_enabled={new_value} to database settings")
            except Exception as e:
                log.warning(f"Failed to save exclude_names_enabled to database: {e}")

            # Update the running dictionary so the setting takes effect immediately
            if old_exclude_names != new_value:
                self.storage.update_exclude_names_setting(new_value)
                log.info(f"Updated dictionary exclude_names setting to {new_value}")

        # Reload dictionary configuration if language settings changed
        if (
            "dictionary_mode" in new_settings
            or "enabled_languages" in new_settings
            or "enabled_dictionaries" in new_settings
            or "exclude_names_enabled" in new_settings
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
            self.signal_update_stats.emit(0, 0, 0, 0, 0)
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

    def provide_digraph_data(self) -> None:
        """Provide digraph data to stats panel."""

        def fetch_data():
            try:
                log.info("Fetching digraph data")
                fastest = self.analyzer.get_fastest_digraphs(
                    limit=10, layout=self.get_current_layout()
                )
                slowest = self.analyzer.get_slowest_digraphs(
                    limit=10, layout=self.get_current_layout()
                )
                log.info(
                    f"Got {len(fastest)} fastest and {len(slowest)} slowest digraphs, emitting signal"
                )
                self.signal_update_digraph_stats.emit(fastest, slowest)
                log.info("Digraph signal emitted successfully")
            except Exception as e:
                log.error(f"Error fetching digraph data: {e}")

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

    def generate_text_with_ollama(self, count: int) -> None:
        """Generate text using Ollama in background thread.

        Args:
            count: Number of words to generate
        """

        def generate_in_thread():
            try:
                # Fetch hardest words
                words = self.analyzer.get_slowest_words(
                    limit=min(count, 100),  # Cap at 100 words
                    layout=self.get_current_layout(),
                )

                if not words:
                    log.warning("No words available for generation")
                    self.signal_text_generation_failed.emit(
                        "No typing data available yet. Type more first!"
                    )
                    return

                # Load prompt template from database
                try:
                    active_prompt_id = self.config.get_int("llm_active_prompt_id", -1)
                    prompt_data = self.storage.get_active_prompt(active_prompt_id)

                    if prompt_data:
                        prompt_template = prompt_data["content"]
                        log.debug(f"Using active prompt: {prompt_data['name']}")
                    else:
                        # Fallback to built-in minimal prompt
                        prompt_template = "Generate a simple typing practice text of approximately {word_count} words using these words: {hardest_words}\n\nCreate a coherent text that includes as many of these words as possible in their natural context. Keep it simple and direct."
                        log.warning("No prompts found, using fallback")

                except Exception as e:
                    log.error(f"Failed to load prompt from database: {e}")
                    # Use fallback prompt
                    prompt_template = "Generate a simple typing practice text of approximately {word_count} words using these words: {hardest_words}\n\nCreate a coherent text that includes as many of these words as possible in their natural context. Keep it simple and direct."

                # Format prompt
                hardest_words = [w.word for w in words[: min(count, 50)]]
                hardest_words_str = ", ".join(hardest_words)
                prompt = prompt_template.format(word_count=count, hardest_words=hardest_words_str)

                # Generate text (OllamaClient handles threading)
                self.ollama_client.generate_text(prompt, hardest_words)

            except Exception as e:
                log.error(f"Error in text generation: {e}")
                self.signal_text_generation_failed.emit(str(e))

        # Submit to thread pool
        self._executor.submit(generate_in_thread)

    def check_ollama_availability(self) -> None:
        """Check Ollama availability and update UI (called periodically)."""

        def check_in_thread():
            available = self.ollama_client.check_server_available()
            # Thread-safe UI update via signal
            self.signal_ollama_available.emit(available)

        self._executor.submit(check_in_thread)

    def start_ollama_monitoring(self) -> None:
        """Start periodic Ollama availability checks."""
        from PySide6.QtCore import QTimer

        self._ollama_check_timer = QTimer()
        self._ollama_check_timer.timeout.connect(self.check_ollama_availability)
        self._ollama_check_timer.start(60000)  # Check every 60 seconds

        # Initial check
        self.check_ollama_availability()

    def practice_hardest_words(self) -> None:
        """Practice hardest words with generated text.

        Generates text using Ollama, then opens typing practice page.
        Uses the 50 hardest words as input for the prompt.
        """
        import subprocess
        from pathlib import Path

        def generate_and_practice():
            try:
                # Always use 50 hardest words for the prompt
                hardest_word_count = 50
                # Use configured word count for how much text to generate
                word_count = self.config.get_int("llm_word_count", 50)

                # Show initial notification (10 second timeout - won't stay open long)
                self.tray_icon.show_notification(
                    "Typing Practice",
                    "Generating practice text with Ollama...",
                    "info",
                    timeout_ms=10000,  # 10 seconds
                )
                log.info(
                    f"Starting typing practice: generating {word_count} words using {hardest_word_count} hardest words"
                )

                # Fetch hardest words (exactly 50 words)
                words = self.analyzer.get_slowest_words(
                    limit=hardest_word_count, layout=self.get_current_layout()
                )

                if not words:
                    log.warning("No words available for typing practice")
                    self.tray_icon.dismiss_notification()
                    self.tray_icon.show_notification(
                        "Typing Practice",
                        "No typing data available yet. Type more first!",
                        "warning",
                    )
                    return

                # Load prompt template from database
                try:
                    active_prompt_id = self.config.get_int("llm_active_prompt_id", -1)
                    prompt_data = self.storage.get_active_prompt(active_prompt_id)

                    if prompt_data:
                        prompt_template = prompt_data["content"]
                        log.debug(f"Using active prompt: {prompt_data['name']}")
                    else:
                        # Fallback to built-in minimal prompt
                        prompt_template = "Generate a simple typing practice text of approximately {word_count} words using these words: {hardest_words}\n\nCreate a coherent text that includes as many of these words as possible in their natural context. Keep it simple and direct."
                        log.warning("No prompts found, using fallback")

                except Exception as e:
                    log.error(f"Failed to load prompt from database: {e}")
                    # Use fallback prompt
                    prompt_template = "Generate a simple typing practice text of approximately {word_count} words using these words: {hardest_words}\n\nCreate a coherent text that includes as many of these words as possible in their natural context. Keep it simple and direct."

                # Format prompt
                hardest_words = [w.word for w in words[:hardest_word_count]]
                hardest_words_str = ", ".join(hardest_words)
                prompt = prompt_template.format(
                    word_count=word_count, hardest_words=hardest_words_str
                )

                log.info(f"Sending prompt to Ollama (target: {word_count} words)")

                # Generate text synchronously (OllamaClient runs in thread)
                generated_text = self.ollama_client.generate_text_sync(prompt, hardest_words)

                if not generated_text:
                    log.warning(
                        "Ollama text generation failed or returned empty, using hardest words directly"
                    )
                    # Fallback: use hardest words directly
                    generated_text = " ".join(hardest_words)

                # Clean up LLM output: remove asterisk markdown formatting
                # This handles cases like *word* or **word** that LLMs sometimes use for emphasis
                generated_text = re.sub(
                    r"\*\*([^*]+)\*\*", r"\1", generated_text
                )  # Remove **word**
                generated_text = re.sub(r"\*([^*]+)\*", r"\1", generated_text)  # Remove *word*
                log.debug("Cleaned LLM output (removed asterisk formatting)")

                actual_word_count = len(generated_text.split())
                log.info(f"Ollama generated {actual_word_count} words")

                # Dismiss the "generating" notification
                self.tray_icon.dismiss_notification()

                # Get the script path
                script_path = Path(__file__).parent / "scripts" / "practice.py"

                if not script_path.exists():
                    log.error(f"practice.py not found at {script_path}")
                    self.tray_icon.dismiss_notification()
                    self.tray_icon.show_notification(
                        "Typing Practice Error", "practice.py script not found", "error"
                    )
                    return

                # Write text to temp file for practice script
                import tempfile

                with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
                    f.write(generated_text)
                    temp_file = f.name

                hardest_words_list = [w.word for w in words[:hardest_word_count]]
                hardest_words_str = ",".join(hardest_words_list)

                log.info(
                    f"Opening typing practice with: {actual_word_count} words, {len(hardest_words_list)} highlighted"
                )

                # Run the practice script with hardest words
                result = subprocess.run(
                    ["python3", str(script_path), "--hardest", temp_file, hardest_words_str],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                # Clean up temp file
                try:
                    Path(temp_file).unlink()
                except:
                    pass

                if result.returncode == 0:
                    log.info("Successfully opened typing practice with generated text")
                else:
                    log.error(f"Failed to open practice: {result.stderr}")
                    self.tray_icon.show_notification(
                        "Typing Practice Error",
                        "Failed to open practice. See logs.",
                        "error",
                        timeout_ms=6000,
                    )

            except subprocess.TimeoutExpired:
                log.error("Practice operation timed out")
                self.tray_icon.dismiss_notification()
                self.tray_icon.show_notification(
                    "Typing Practice Error", "Operation timed out", "error", timeout_ms=6000
                )
            except Exception as e:
                log.error(f"Error in practice_hardest_words: {e}")
                self.tray_icon.dismiss_notification()
                self.tray_icon.show_notification(
                    "Typing Practice Error", f"Error: {str(e)}", "error"
                )

        # Run in background thread
        self._executor.submit(generate_and_practice)

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
                    log.debug(f"Processing key event: {key_type}")
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
        if self._stats_panel_visible:
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
        start_time = time.time()
        log.info("update_statistics() called")

        stats = self.analyzer.get_statistics()
        long_term_avg = self.analyzer.get_long_term_average_wpm() or 0
        all_time_best = self.analyzer.get_all_time_high_score() or 0
        wpm_95th_percentile = self.analyzer.get_burst_wpm_percentile(95) or 0

        log.info(f"get_statistics took {(time.time() - start_time) * 1000:.1f}ms")

        log.info(
            f"Emitting stats signal: burst_wpm={stats['burst_wpm']:.1f}, today_best={stats['personal_best_today'] or 0:.1f}"
        )
        self.signal_update_stats.emit(
            stats["burst_wpm"],
            stats["personal_best_today"] or 0,
            long_term_avg,
            all_time_best,
            wpm_95th_percentile,
        )

        keys_start = time.time()
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
        log.info(f"Slowest/fastest keys queries took {(time.time() - keys_start) * 1000:.1f}ms")

        words_start = time.time()
        hardest_words = self.analyzer.get_slowest_words(limit=10, layout=self.get_current_layout())
        self.signal_update_hardest_words.emit(hardest_words)

        fastest_words = self.analyzer.get_fastest_words(limit=10, layout=self.get_current_layout())
        self.signal_update_fastest_words_stats.emit(fastest_words)
        log.info(f"Slowest/fastest words queries took {(time.time() - words_start) * 1000:.1f}ms")

        # Update digraph statistics
        digraphs_start = time.time()
        fastest_digraphs = self.analyzer.get_fastest_digraphs(
            limit=10, layout=self.get_current_layout()
        )
        slowest_digraphs = self.analyzer.get_slowest_digraphs(
            limit=10, layout=self.get_current_layout()
        )
        self.signal_update_digraph_stats.emit(fastest_digraphs, slowest_digraphs)
        log.info(f"Digraph queries took {(time.time() - digraphs_start) * 1000:.1f}ms")

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
        avg_ms, min_ms, max_ms, percentile_95_ms = self.storage.get_burst_duration_stats_ms()
        self.signal_update_avg_burst_duration.emit(
            avg_ms, min_ms, max_ms, percentile_95_ms, wpm_95th_percentile
        )

        total_time = (time.time() - start_time) * 1000
        log.info(f"update_statistics() completed in {total_time:.1f}ms")

    def _health_check(self) -> None:
        """Periodic health check logging - runs every 5 minutes regardless of panel state."""
        import os

        # Get memory usage from /proc (Linux)
        try:
            with open(f"/proc/{os.getpid()}/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        mem_kb = int(line.split()[1])
                        mem_mb = mem_kb / 1024
                        break
        except Exception:
            mem_mb = 0

        queue_size = self.event_queue.qsize()
        timer_interval = self.process_queue_timer.interval()

        log.info(
            f"=== HEALTH CHECK === Memory: {mem_mb:.1f}MB | Queue: {queue_size} | "
            f"Timer: {timer_interval}ms | Panel visible: {self._stats_panel_visible} ==="
        )

        # Sample expensive queries to track performance over time
        start = time.time()
        try:
            self.storage.get_slowest_keys(limit=10, layout=self.get_current_layout())
            query_time = (time.time() - start) * 1000
            log.info(f"HEALTH: Slowest keys query took {query_time:.1f}ms")
        except Exception as e:
            log.warning(f"HEALTH: Query test failed: {e}")

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
            "max_realistic_wpm": self.config.get_int("max_realistic_wpm", 300),
            "unrealistic_speed_warning_enabled": self.config.get_bool(
                "unrealistic_speed_warning_enabled", True
            ),
            "data_retention_days": self.config.get_int("data_retention_days", -1),
            "dictionary_mode": self.config.get("dictionary_mode", "validate"),
            "enabled_languages": self.config.get("enabled_languages", "en,de"),
            "enabled_dictionaries": enabled_dicts_value,
            "exclude_names_enabled": self.config.get_bool("exclude_names_enabled", False),
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
            # LLM settings
            "llm_model": self.config.get("llm_model", "gemma2:2b"),
            "llm_active_prompt_id": self.config.get_int("llm_active_prompt_id", -1),
            "llm_word_count": self.config.get_int("llm_word_count", 50),
        }
        dialog = SettingsDialog(
            current_settings, storage=self.storage, sync_handler=self.sync_handler
        )

        # Set Ollama availability and fetch available models
        dialog.set_ollama_available(self.ollama_client.check_server_available())
        if self.ollama_client.check_server_available():
            models = self.ollama_client.list_models()
            dialog._available_models = models

        if dialog.exec() == QDialog.Accepted:
            # Use dialog.settings if it was set by clear_data/export_csv, otherwise get fresh settings
            if dialog.settings:
                new_settings = dialog.settings
            else:
                new_settings = dialog.get_settings()
            self.apply_settings(new_settings)

            # Refresh model if it changed
            if "llm_model" in new_settings:
                new_model = new_settings["llm_model"]
                if new_model != self.ollama_client.model:
                    # Stop the current model before switching
                    self.ollama_client.stop_model()
                    self.ollama_client.model = new_model
                    log.info(f"LLM model changed to: {new_model}")

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
        if self._stats_panel_visible:
            self.update_statistics()

        log.info("Starting notification handler...")
        self.notification_handler.start()

        # Start sync handler if enabled
        if self.sync_handler.enabled:
            log.info("Starting sync handler...")
            self.sync_handler.start()

        # Start Ollama availability monitoring
        log.info("Starting Ollama availability monitoring...")
        self.start_ollama_monitoring()

        self.process_queue_timer = QTimer()
        self.process_queue_timer.timeout.connect(self.process_event_queue)
        self.process_queue_timer.start(500)  # Check every 500ms

        # Periodic health check timer (logs diagnostics every 5 minutes)
        self._health_check_timer = QTimer()
        self._health_check_timer.timeout.connect(self._health_check)
        self._health_check_timer.start(300000)  # Every 5 minutes

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
