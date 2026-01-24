"""About dialog for RealTypeCoach."""

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from core.version import __version__


class ClickableUrlLabel(QLabel):
    """A label that opens a URL when clicked."""

    def __init__(self, text: str, url: str, parent=None):
        """Initialize clickable URL label.

        Args:
            text: Label text to display
            url: URL to open when clicked
            parent: Parent widget
        """
        super().__init__(text, parent)
        self.url = QUrl(url)
        self.setStyleSheet("color: #0066cc; text-decoration: underline;")
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        """Open URL when clicked."""
        QDesktopServices.openUrl(self.url)


class AboutDialog(QDialog):
    """About dialog showing version and application info."""

    def __init__(self, parent=None):
        """Initialize about dialog.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.init_ui()

    def init_ui(self) -> None:
        """Initialize user interface."""
        self.setWindowTitle("About RealTypeCoach")
        self.setMinimumWidth(400)

        # Set window flags for Wayland compatibility
        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)

        layout = QVBoxLayout()

        # Application name (large, bold)
        title_label = QLabel("RealTypeCoach")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        # Description
        desc_label = QLabel(
            "KDE Wayland typing analysis application\n"
            "Track your typing speed and improve your skills"
        )
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        layout.addSpacing(20)

        # Version information
        version_title = QLabel("Version:")
        version_title_font = QFont()
        version_title_font.setBold(True)
        version_title.setFont(version_title_font)
        version_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version_title)

        version_label = QLabel(__version__)
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(version_label)

        layout.addSpacing(10)

        # GitHub link
        github_link = ClickableUrlLabel(
            "📦 GitHub Repository", "https://github.com/Dronakurl/realtypecoach"
        )
        github_link.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(github_link)

        layout.addSpacing(20)

        # Additional info
        info_label = QLabel(
            "Built with PySide6\n"
            "Database: SQLite with SQLCipher encryption\n"
            "Keyboard event capture via evdev"
        )
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #888; font-size: 10px;")
        layout.addWidget(info_label)

        layout.addStretch()

        # Close button
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(close_button)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        self.setLayout(layout)
