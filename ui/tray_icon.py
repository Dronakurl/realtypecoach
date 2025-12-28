"""System tray icon for RealTypeCoach."""

from PyQt5.QtWidgets import (QSystemTrayIcon, QMenu, QAction,
                             QApplication, QMessageBox, QDialog)
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QTimer
from pathlib import Path
import sys
sys.path.insert(0, '.')

from ui.stats_panel import StatsPanel
from ui.settings_dialog import SettingsDialog


class TrayIcon(QSystemTrayIcon):
    """System tray icon for RealTypeCoach."""

    settings_changed = pyqtSignal(dict)
    stats_requested = pyqtSignal()  # Emitted when stats panel is requested

    def __init__(self, stats_panel: StatsPanel,
                 icon_path: Path, icon_paused_path: Path, icon_stopping_path: Path,
                 parent=None):
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
            3000
        )

    def create_menu(self) -> None:
        """Create context menu."""
        menu = QMenu()

        show_stats_action = QAction("📊 Show Statistics", self)
        show_stats_action.triggered.connect(self.show_stats)
        menu.addAction(show_stats_action)

        menu.addSeparator()

        self.pause_action = QAction("⏸ Pause Monitoring", self)
        self.pause_action.triggered.connect(self.toggle_monitoring)
        menu.addAction(self.pause_action)

        menu.addSeparator()

        settings_action = QAction("⚙️ Settings", self)
        settings_action.triggered.connect(self.show_settings_dialog)
        menu.addAction(settings_action)

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
                2000
            )
        else:
            self.pause_action.setText("▶️ Resume Monitoring")
            self.setIcon(QIcon(str(self.icon_paused_path)))
            self.setToolTip("RealTypeCoach - Monitoring Paused")
            self.showMessage(
                "Monitoring Paused",
                "RealTypeCoach is not recording typing.",
                QSystemTrayIcon.MessageIcon.Warning,
                2000
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
        """Show settings dialog."""
        dialog = SettingsDialog({})
        if dialog.exec_() == QDialog.Accepted:
            new_settings = dialog.get_settings()
            self.settings_changed.emit(new_settings)

    def show_notification(self, title: str, message: str,
                       message_type: str = "info") -> None:
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
