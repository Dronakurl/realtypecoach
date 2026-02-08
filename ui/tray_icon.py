"""System tray icon for RealTypeCoach."""

from pathlib import Path

from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from ui.stats_panel import StatsPanel


class TrayIcon(QSystemTrayIcon):
    """System tray icon for RealTypeCoach."""

    settings_changed = Signal(dict)
    settings_requested = Signal()  # Emitted when settings dialog is requested
    stats_requested = Signal()  # Emitted when stats panel is requested
    about_requested = Signal()  # Emitted when about dialog is requested
    monkeytype_practice_requested = Signal()  # Emitted when Monkeytype practice is requested

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

        self.create_menu()
        self.showMessage(
            "RealTypeCoach",
            "Typing analysis started. Click icon for stats!",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )

    def create_menu(self) -> None:
        """Create context menu."""
        menu = QMenu()

        show_stats_action = QAction("📊 Show Statistics", self)
        show_stats_action.triggered.connect(self.show_stats)
        menu.addAction(show_stats_action)

        monkeytype_action = QAction("🐵 Practice Hardest Words in Monkeytype", self)
        monkeytype_action.triggered.connect(self.practice_hardest_words_monkeytype)
        menu.addAction(monkeytype_action)

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

    def practice_hardest_words_monkeytype(self) -> None:
        """Practice hardest 10 words in Monkeytype."""
        self.monkeytype_practice_requested.emit()

    def toggle_monitoring(self) -> None:
        """Toggle monitoring on/off."""
        self.monitoring_active = not self.monitoring_active

        if self.monitoring_active:
            self.pause_action.setText("⏸ Pause Monitoring")
            self.setIcon(QIcon(str(self.icon_path)))
            self.setToolTip("RealTypeCoach - Monitoring Active")
            self.showMessage(
                "Monitoring Resumed",
                "RealTypeCoach is now recording your typing!",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )
        else:
            self.pause_action.setText("▶️ Resume Monitoring")
            self.setIcon(QIcon(str(self.icon_paused_path)))
            self.setToolTip("RealTypeCoach - Monitoring Paused")
            self.showMessage(
                "Monitoring Paused",
                "RealTypeCoach is not recording typing.",
                QSystemTrayIcon.MessageIcon.Warning,
                2000,
            )

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

    def show_notification(self, title: str, message: str, message_type: str = "info") -> None:
        """Show desktop notification.

        Args:
            title: Notification title
            message: Notification message
            message_type: Type of notification (info/warning/error)
        """
        icon_type = QSystemTrayIcon.MessageIcon.Information
        if message_type == "warning":
            icon_type = QSystemTrayIcon.MessageIcon.Warning
        elif message_type == "error":
            icon_type = QSystemTrayIcon.MessageIcon.Critical

        self.showMessage(title, message, icon_type, 5000)
