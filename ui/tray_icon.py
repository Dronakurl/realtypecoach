"""System tray icon for RealTypeCoach."""

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Q_ARG, QMetaObject, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

if TYPE_CHECKING:
    from ui.stats_panel import StatsPanel


class TrayIcon(QSystemTrayIcon):
    """System tray icon for RealTypeCoach."""

    settings_changed = Signal(dict)
    settings_requested = Signal()  # Emitted when settings dialog is requested
    stats_requested = Signal()  # Emitted when stats panel is requested
    about_requested = Signal()  # Emitted when about dialog is requested
    practice_requested = Signal()  # Emitted when AI typing practice is requested
    digraphs_practice_requested = Signal()  # Emitted when digraph practice is requested
    words_practice_requested = Signal()  # Emitted when word practice is requested
    clipboard_practice_requested = Signal()  # Emitted when clipboard practice is requested
    sync_requested = Signal()  # Emitted when database sync is requested
    dismiss_notification_requested = Signal()  # Emitted to dismiss current notification
    menu_opened = Signal()  # Emitted before the tray context menu is shown

    def __init__(
        self,
        stats_panel: "StatsPanel | None",
        icon_path: Path,
        icon_paused_path: Path,
        icon_stopping_path: Path,
        parent=None,
    ):
        """Initialize tray icon.

        Args:
            stats_panel: Statistics panel widget
            icon_path: Path to active icon file
            icon_paused_path: Path to paused icon file
            icon_stopping_path: Path to stopping icon file
            parent: Parent widget
        """
        super().__init__(parent)
        self.stats_panel = stats_panel
        self.icon_path = icon_path
        self.icon_paused_path = icon_paused_path
        self.icon_stopping_path = icon_stopping_path
        self.monitoring_active = True
        self.ollama_available = False
        self.dictionary_count = 0
        self._menu = None
        self._monkeytype_icon = QIcon(
            str(Path(__file__).parent.parent / "icons" / "monkeytype.png")
        )

        self.setIcon(QIcon(str(icon_path)))
        self.setToolTip("RealTypeCoach - Monitoring Active")

        # Connect internal signals
        self.dismiss_notification_requested.connect(self._do_dismiss_notification)

        self.create_menu()

    def set_ollama_available(self, available: bool) -> None:
        """Update Ollama availability without rebuilding the tray menu.

        Args:
            available: True if Ollama is available
        """
        if self.ollama_available == available:
            return
        self.ollama_available = available
        self._update_ollama_action_visibility()

    def set_dictionary_count(self, count: int) -> None:
        """Update dictionary count without rebuilding the tray menu.

        Args:
            count: Number of available dictionaries
        """
        if self.dictionary_count == count:
            return
        self.dictionary_count = count
        self._update_dictionary_warning_visibility()

    def create_menu(self) -> None:
        """Create context menu."""
        if self._menu is not None:
            self._update_ollama_action_visibility()
            return

        menu = QMenu()
        menu.aboutToShow.connect(self.menu_opened.emit)

        self.dictionary_warning_action = QAction("⚠️ No Dictionaries Found", self)
        self.dictionary_warning_action.setEnabled(False)
        menu.addAction(self.dictionary_warning_action)

        show_stats_action = QAction("📊 Show Statistics", self)
        show_stats_action.triggered.connect(self.show_stats)
        menu.addAction(show_stats_action)

        practice_digraphs_action = QAction("🐵 Practice Digraphs", self)
        practice_digraphs_action.setIcon(self._monkeytype_icon)
        practice_digraphs_action.triggered.connect(self.practice_digraphs)
        menu.addAction(practice_digraphs_action)

        practice_words_action = QAction("🐵 Practice Words", self)
        practice_words_action.setIcon(self._monkeytype_icon)
        practice_words_action.triggered.connect(self.practice_words)
        menu.addAction(practice_words_action)

        practice_clipboard_action = QAction("📋 Practice Clipboard", self)
        practice_clipboard_action.setIcon(self._monkeytype_icon)
        practice_clipboard_action.triggered.connect(self.practice_clipboard)
        menu.addAction(practice_clipboard_action)

        self.practice_ai_action = QAction("✨ AI Practice", self)
        self.practice_ai_action.setIcon(self._monkeytype_icon)
        self.practice_ai_action.triggered.connect(self.practice_ai)
        menu.addAction(self.practice_ai_action)

        settings_action = QAction("⚙️ Settings", self)
        settings_action.triggered.connect(self.show_settings_dialog)
        menu.addAction(settings_action)

        sync_action = QAction("🔄 Sync Database", self)
        sync_action.triggered.connect(self.sync_database)
        menu.addAction(sync_action)

        about_action = QAction("ℹ️ About", self)
        about_action.triggered.connect(self.show_about_dialog)
        menu.addAction(about_action)

        menu.addSeparator()

        self.pause_action = QAction("⏸ Pause Monitoring", self)
        self.pause_action.triggered.connect(self.toggle_monitoring)
        menu.addAction(self.pause_action)

        menu.addSeparator()

        quit_action = QAction("❌ Quit", self)
        quit_action.triggered.connect(self._quit_app)
        menu.addAction(quit_action)

        self._menu = menu
        self.setContextMenu(menu)
        self._update_dictionary_warning_visibility()
        self._update_ollama_action_visibility()

    def _update_ollama_action_visibility(self) -> None:
        """Show or hide AI-specific actions based on current availability."""
        if hasattr(self, "practice_ai_action"):
            self.practice_ai_action.setVisible(self.ollama_available)

    def _update_dictionary_warning_visibility(self) -> None:
        """Show the missing-dictionary warning only when no dictionaries are loaded."""
        if hasattr(self, "dictionary_warning_action"):
            self.dictionary_warning_action.setVisible(self.dictionary_count == 0)

    def show_stats(self) -> None:
        """Show statistics panel."""
        self.stats_requested.emit()

    def set_stats_panel(self, stats_panel: "StatsPanel") -> None:
        """Attach the lazily created statistics panel."""
        self.stats_panel = stats_panel

    def practice_digraphs(self) -> None:
        """Practice digraphs with settings from statistics panel."""
        self.digraphs_practice_requested.emit()

    def practice_words(self) -> None:
        """Practice words with settings from statistics panel."""
        self.words_practice_requested.emit()

    def practice_clipboard(self) -> None:
        """Practice with clipboard contents."""
        self.clipboard_practice_requested.emit()

    def practice_ai(self) -> None:
        """Practice with AI-generated text using Ollama."""
        self.practice_requested.emit()

    def restore_tooltip(self) -> None:
        """Restore tooltip to its normal state."""
        if self.monitoring_active:
            self.setToolTip("RealTypeCoach - Monitoring Active")
        else:
            self.setToolTip("RealTypeCoach - Monitoring Paused")

    def toggle_monitoring(self) -> None:
        """Toggle monitoring on/off."""
        self.monitoring_active = not self.monitoring_active

        if self.monitoring_active:
            self.pause_action.setText("⏸ Pause Monitoring")
            self.setIcon(QIcon(str(self.icon_path)))
            self.setToolTip("RealTypeCoach - Monitoring Active")
        else:
            self.pause_action.setText("▶️ Resume Monitoring")
            self.setIcon(QIcon(str(self.icon_paused_path)))
            self.setToolTip("RealTypeCoach - Monitoring Paused")

    def _quit_app(self) -> None:
        """Quit the application."""
        # Show stopping icon
        self.setIcon(QIcon(str(self.icon_stopping_path)))
        self.setToolTip("RealTypeCoach - Stopping...")

        # Process events to ensure icon updates
        QApplication.processEvents()

        # Delay quit slightly so the stopping icon is visible
        QTimer.singleShot(100, self._do_quit)

    def _do_quit(self) -> None:
        """Actually quit the application after delay."""
        if QApplication.instance():
            QApplication.instance().quit()
        else:
            import sys

            sys.exit(0)

    def show_settings_dialog(self) -> None:
        """Request settings dialog to be shown."""
        self.settings_requested.emit()

    def show_about_dialog(self) -> None:
        """Show about dialog."""
        self.about_requested.emit()

    def sync_database(self) -> None:
        """Request database sync."""
        self.sync_requested.emit()

    def show_notification(
        self, title: str, message: str, message_type: str = "info", timeout_ms: int = 3000
    ) -> None:
        """Show desktop notification.

        Thread-safe method that can be called from any thread.

        Args:
            title: Notification title
            message: Notification message
            message_type: Type of notification (info/warning/error)
            timeout_ms: Timeout in milliseconds (0 = indefinite/stays until clicked)
        """
        # Use invokeMethod to ensure this runs on the GUI thread
        QMetaObject.invokeMethod(
            self,
            "_do_show_notification",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(str, title),
            Q_ARG(str, message),
            Q_ARG(int, timeout_ms),
        )

    @Slot(str, str, int)
    def _do_show_notification(self, title: str, message: str, timeout_ms: int = 3000) -> None:
        """Internal method to show notification on GUI thread.

        Args:
            title: Notification title
            message: Notification message
            timeout_ms: Timeout in milliseconds (0 = indefinite/stays until clicked)
        """
        # Show notification (Qt handles icon restoration automatically)
        self.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, timeout_ms)

    def dismiss_notification(self) -> None:
        """Dismiss the current notification by showing a brief empty message.

        Thread-safe method that can be called from any thread.
        """
        self.dismiss_notification_requested.emit()

    @Slot()
    def _do_dismiss_notification(self) -> None:
        """Internal method to dismiss notification on GUI thread."""
        # Show an empty message with minimal timeout to clear any existing notification
        self.showMessage("", "", QSystemTrayIcon.MessageIcon.Information, 1)
