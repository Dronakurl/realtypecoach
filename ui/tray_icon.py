"""System tray icon for RealTypeCoach."""

from pathlib import Path

from PySide6.QtCore import Q_ARG, QMetaObject, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from ui.stats_panel import StatsPanel


class TrayIcon(QSystemTrayIcon):
    """System tray icon for RealTypeCoach."""

    settings_changed = Signal(dict)
    settings_requested = Signal()  # Emitted when settings dialog is requested
    stats_requested = Signal()  # Emitted when stats panel is requested
    about_requested = Signal()  # Emitted when about dialog is requested
    practice_requested = Signal()  # Emitted when typing practice is requested
    dismiss_notification_requested = Signal()  # Emitted to dismiss current notification

    def __init__(
        self,
        stats_panel: StatsPanel,
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

        self.setIcon(QIcon(str(icon_path)))
        self.setToolTip("RealTypeCoach - Monitoring Active")

        # Connect internal signals
        self.dismiss_notification_requested.connect(self._do_dismiss_notification)

        self.create_menu()

    def create_menu(self) -> None:
        """Create context menu."""
        menu = QMenu()

        show_stats_action = QAction("📊 Show Statistics", self)
        show_stats_action.triggered.connect(self.show_stats)
        menu.addAction(show_stats_action)

        practice_action = QAction("⌨️ Practice Hardest Words", self)
        practice_action.triggered.connect(self.practice_hardest_words)
        menu.addAction(practice_action)

        settings_action = QAction("⚙️ Settings", self)
        settings_action.triggered.connect(self.show_settings_dialog)
        menu.addAction(settings_action)

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

        self.setContextMenu(menu)

    def show_stats(self) -> None:
        """Show statistics panel."""
        self.stats_requested.emit()  # Request fresh statistics
        self.stats_panel.show()
        self.stats_panel.raise_()
        self.stats_panel.activateWindow()

    def practice_hardest_words(self) -> None:
        """Practice hardest words with generated text."""
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

    def show_notification(self, title: str, message: str, message_type: str = "info", timeout_ms: int = 3000) -> None:
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
