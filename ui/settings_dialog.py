"""Settings dialog for RealTypeCoach."""

import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
    QStyle,
    QTabWidget,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

log = logging.getLogger("realtypecoach.settings_dialog")


class ClickableInfoLabel(QLabel):
    """A label that shows its tooltip on both hover and click."""

    def __init__(self, text: str, tooltip_text: str, parent=None):
        """Initialize clickable info label.

        Args:
            text: Label text (e.g., " ⓘ")
            tooltip_text: Tooltip text to show on hover/click
            parent: Parent widget
        """
        super().__init__(text, parent)
        self._tooltip_text = tooltip_text
        self.setToolTip(tooltip_text)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        """Show tooltip on click.

        Shows the tooltip at the click position when the info icon is clicked.
        """
        if event.button() == Qt.LeftButton:
            QToolTip.showText(
                event.globalPosition().toPoint(),
                self._tooltip_text,
                self,
            )
        super().mousePressEvent(event)


class SettingsDialog(QDialog):
    """Configuration dialog for RealTypeCoach."""

    def __init__(self, current_settings: dict, storage=None, sync_handler=None, parent=None):
        """Initialize settings dialog.

        Args:
            current_settings: Dictionary of current settings
            storage: Optional Storage instance for sync operations
            sync_handler: Optional SyncHandler for auto-sync status
            parent: Parent widget
        """
        super().__init__(parent)
        self.current_settings = current_settings
        self.storage = storage
        self.sync_handler = sync_handler
        self.settings: dict = {}
        # Set window flags for Wayland compatibility
        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        self.init_ui()
        self.load_current_settings()
        # Connect sync signals after UI is initialized
        self._connect_sync_signals()

    @staticmethod
    def _create_palette_aware_icon(theme_name: str) -> QIcon:
        """Create an icon that automatically adapts to light/dark theme.

        Uses the palette's text color to colorize the icon, ensuring
        visibility in both light and dark themes.

        Args:
            theme_name: Icon theme name (e.g., 'view-refresh')

        Returns:
            QIcon colored with palette text color
        """
        # Direct mapping to Qt standard icons for all tabs
        style = QApplication.style()
        icon_map = {
            "preferences-system": QStyle.SP_BrowserReload,  # Settings/configure
            "preferences-desktop-notification": QStyle.SP_DialogApplyButton,  # Notify/alert
            "database": QStyle.SP_DriveHDIcon,  # Storage/database
            "accessories-dictionary": QStyle.SP_FileDialogDetailedView,  # Language/list
        }

        if theme_name in icon_map:
            icon = style.standardIcon(icon_map[theme_name])
        else:
            icon = QIcon.fromTheme(theme_name)

            # Fallback to Qt standard icons if theme icon is not available
            if icon.isNull():
                fallback_map = {
                    "preferences-desktop-notification": QStyle.SP_DialogHelpButton,
                    "database": QStyle.SP_FileIcon,
                    "accessories-dictionary": QStyle.SP_FileIcon,
                }
                if theme_name in fallback_map:
                    icon = style.standardIcon(fallback_map[theme_name])
                if icon.isNull():
                    # Last resort: create text-based icon
                    return SettingsDialog._create_text_icon(theme_name)

        # Get the application's palette text color for colorization
        palette = QApplication.palette()
        # Use WindowText instead of Text for tab bar visibility
        text_color = palette.color(QPalette.WindowText)

        # Colorize the icon for multiple sizes
        colorized_icon = QIcon()
        sizes = [16, 22, 24, 32]
        has_valid_pixmap = False

        for size in sizes:
            pixmap = icon.pixmap(size, size)
            if pixmap.isNull():
                continue

            # Convert to image for pixel manipulation
            image = pixmap.toImage().convertToFormat(QImage.Format_ARGB32)

            # Colorize: replace non-transparent pixels with palette text color
            for y in range(image.height()):
                for x in range(image.width()):
                    color = image.pixelColor(x, y)
                    if color.alpha() > 0:
                        # Keep original alpha but use palette text color
                        new_color = QColor(text_color)
                        new_color.setAlpha(color.alpha())
                        image.setPixelColor(x, y, new_color)

            # Create pixmap from colorized image
            colorized_pixmap = QPixmap.fromImage(image)

            # Add to icon with proper modes
            colorized_icon.addPixmap(colorized_pixmap, QIcon.Normal, QIcon.On)
            colorized_icon.addPixmap(colorized_pixmap, QIcon.Active, QIcon.On)
            colorized_icon.addPixmap(colorized_pixmap, QIcon.Selected, QIcon.On)
            has_valid_pixmap = True

        # If colorization failed, create text-based icon
        if not has_valid_pixmap:
            return SettingsDialog._create_text_icon(theme_name)

        return colorized_icon

    @staticmethod
    def _create_text_icon(theme_name: str) -> QIcon:
        """Create a text-based icon as last resort fallback.

        Args:
            theme_name: Icon theme name to map to text symbol

        Returns:
            QIcon with text symbol
        """
        # Map theme names to emoji/text symbols
        symbol_map = {
            "preferences-system": "⚙",
            "preferences-desktop-notification": "🔔",
            "database": "🗁",
            "accessories-dictionary": "📖",
        }
        symbol = symbol_map.get(theme_name, "•")

        # Use window text color which should be visible in the tab bar
        palette = QApplication.palette()
        text_color = palette.color(QPalette.WindowText)
        if text_color.lightness() > 200:
            # If color is too light (white on light theme), use a darker color
            text_color = QColor(60, 60, 60)

        # Create pixmap with text symbol
        pixmap = QPixmap(22, 22)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setPen(text_color)
        font = painter.font()
        font.setPixelSize(16)
        painter.setFont(font)

        # Center text
        rect = pixmap.rect()
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, symbol)
        painter.end()

        return QIcon(pixmap)

    @staticmethod
    def _create_labeled_icon_widget(label_text: str, tooltip_text: str, parent=None) -> QWidget:
        """Create a label with integrated info icon and tooltip.

        Args:
            label_text: The text for the label (e.g., "Burst timeout:")
            tooltip_text: The tooltip text to show on info icon hover
            parent: Parent widget

        Returns:
            QWidget containing the label and info icon in a horizontal layout
        """
        from PySide6.QtWidgets import QWidget as QtWidgetsWidget

        container = QtWidgetsWidget(parent)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Create the text label
        text_label = QLabel(label_text, parent)
        layout.addWidget(text_label)

        # Create the info icon label using Unicode circled i (standard info icon)
        info_label = ClickableInfoLabel(" ⓘ", tooltip_text, parent)
        info_label.setStyleSheet("font-size: 14px; color: palette(text);")
        layout.addWidget(info_label)

        layout.addStretch()
        return container

    def init_ui(self) -> None:
        """Initialize user interface."""
        self.setWindowTitle("RealTypeCoach Settings")
        self.setMinimumWidth(500)

        layout = QVBoxLayout()

        tabs = QTabWidget()
        layout.addWidget(tabs)

        general_tab = self.create_general_tab()
        tabs.addTab(general_tab, "General")
        tabs.setTabIcon(0, self._create_palette_aware_icon("preferences-system"))

        notification_tab = self.create_notification_tab()
        tabs.addTab(notification_tab, "Notifications")
        tabs.setTabIcon(1, self._create_palette_aware_icon("preferences-desktop-notification"))

        data_tab = self.create_data_tab()
        tabs.addTab(data_tab, "Data")
        tabs.setTabIcon(2, self._create_palette_aware_icon("database"))

        language_tab = self.create_language_tab()
        tabs.addTab(language_tab, "Language")
        tabs.setTabIcon(3, self._create_palette_aware_icon("accessories-dictionary"))

        database_tab = self.create_database_tab()
        tabs.addTab(database_tab, "Database")
        tabs.setTabIcon(4, self._create_palette_aware_icon("network-server"))

        dialog_buttons = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        dialog_buttons.addWidget(ok_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        dialog_buttons.addWidget(cancel_btn)

        layout.addLayout(dialog_buttons)
        self.setLayout(layout)

    def _connect_sync_signals(self) -> None:
        """Connect sync handler signals."""
        if self.sync_handler:
            from PySide6.QtCore import Qt

            self.sync_handler.signal_sync_completed.connect(
                self._on_sync_completed,
                Qt.ConnectionType.QueuedConnection,
            )

        # Connect checkbox to update next sync label
        self.auto_sync_enabled_check.stateChanged.connect(self._update_next_sync_label)
        self.sync_interval_spin.valueChanged.connect(self._update_next_sync_label)

    def create_general_tab(self) -> QWidget:
        """Create general settings tab."""
        widget = QWidget()
        layout = QVBoxLayout()

        burst_group = QGroupBox("Burst Detection")
        burst_layout = QFormLayout()

        self.burst_timeout_spin = QSpinBox()
        self.burst_timeout_spin.setRange(100, 10000)
        self.burst_timeout_spin.setSuffix(" ms")
        self.burst_timeout_spin.setValue(1000)
        burst_layout.addRow(
            self._create_labeled_icon_widget(
                "Burst timeout:",
                "Maximum pause between keystrokes before burst ends.\n"
                "Shorter timeout = bursts split more frequently",
            ),
            self.burst_timeout_spin,
        )

        self.word_boundary_timeout_spin = QSpinBox()
        self.word_boundary_timeout_spin.setRange(100, 10000)
        self.word_boundary_timeout_spin.setSuffix(" ms")
        self.word_boundary_timeout_spin.setValue(1000)
        burst_layout.addRow(
            self._create_labeled_icon_widget(
                "Word boundary timeout:",
                "Maximum pause between letters before word is split.\n"
                "Example: 'br' [pause] 'own' becomes two fragments instead of 'brown'\n"
                "Shorter timeout = more conservative word detection",
            ),
            self.word_boundary_timeout_spin,
        )

        self.duration_method_combo = QComboBox()
        self.duration_method_combo.addItem("Total Time (includes pauses)", "total_time")
        self.duration_method_combo.addItem("Active Time (typing only)", "active_time")
        burst_layout.addRow(
            self._create_labeled_icon_widget(
                "Duration calculation:",
                "How burst duration is calculated:\n"
                "• Total Time: Includes all time from first to last keystroke\n"
                "• Active Time: Only counts time actually spent typing",
            ),
            self.duration_method_combo,
        )

        self.active_threshold_spin = QSpinBox()
        self.active_threshold_spin.setRange(100, 2000)
        self.active_threshold_spin.setSuffix(" ms")
        self.active_threshold_spin.setValue(500)
        burst_layout.addRow(
            self._create_labeled_icon_widget(
                "Active time threshold:",
                "For 'Active Time' method: Maximum gap between keystrokes\n"
                "to count as active typing time.",
            ),
            self.active_threshold_spin,
        )

        self.high_score_duration_spin = QSpinBox()
        self.high_score_duration_spin.setRange(5000, 60000)
        self.high_score_duration_spin.setSuffix(" ms")
        self.high_score_duration_spin.setValue(5000)
        burst_layout.addRow(
            self._create_labeled_icon_widget(
                "High score min duration:",
                "Minimum burst duration to qualify for high score notifications",
            ),
            self.high_score_duration_spin,
        )

        self.min_key_count_spin = QSpinBox()
        self.min_key_count_spin.setRange(1, 100)
        self.min_key_count_spin.setSuffix(" keys")
        self.min_key_count_spin.setValue(10)
        burst_layout.addRow(
            self._create_labeled_icon_widget(
                "Min burst key count:",
                "Minimum keystrokes required for a burst to be recorded.\n"
                "Prevents keyboard shortcuts and brief typing from being counted.",
            ),
            self.min_key_count_spin,
        )

        self.min_burst_duration_spin = QSpinBox()
        self.min_burst_duration_spin.setRange(1000, 30000)
        self.min_burst_duration_spin.setSuffix(" ms")
        self.min_burst_duration_spin.setValue(5000)
        burst_layout.addRow(
            self._create_labeled_icon_widget(
                "Min burst duration:",
                "Minimum duration for a burst to be recorded.\n"
                "Prevents very short typing sessions from being counted.",
            ),
            self.min_burst_duration_spin,
        )

        burst_group.setLayout(burst_layout)
        layout.addWidget(burst_group)

        keyboard_group = QGroupBox("Keyboard")
        keyboard_layout = QFormLayout()

        self.keyboard_layout_combo = QComboBox()
        self.keyboard_layout_combo.addItem("Auto-detect", "auto")
        self.keyboard_layout_combo.addItem("US (QWERTY)", "us")
        self.keyboard_layout_combo.addItem("German (QWERTZ)", "de")
        keyboard_layout.addRow(
            self._create_labeled_icon_widget(
                "Layout:",
                "Choose your keyboard layout for accurate key mapping.\n"
                "Auto-detect uses system locale.",
            ),
            self.keyboard_layout_combo,
        )

        # Add detected layout hint
        self.detected_layout_label = QLabel()
        self.detected_layout_label.setWordWrap(True)
        self.detected_layout_label.setStyleSheet("color: #666; font-style: italic;")
        keyboard_layout.addRow("", self.detected_layout_label)

        keyboard_group.setLayout(keyboard_layout)
        layout.addWidget(keyboard_group)

        # Detect and show current layout
        self._update_detected_layout()

        display_group = QGroupBox("Display")
        display_layout = QFormLayout()

        self.stats_update_interval_spin = QSpinBox()
        self.stats_update_interval_spin.setRange(1, 60)
        self.stats_update_interval_spin.setSuffix(" s")
        self.stats_update_interval_spin.setValue(2)
        display_layout.addRow(
            self._create_labeled_icon_widget(
                "Statistics update interval:",
                "How often the statistics window updates with new data.\n"
                "Shorter interval = more frequent updates, but more CPU usage.",
            ),
            self.stats_update_interval_spin,
        )

        display_group.setLayout(display_layout)
        layout.addWidget(display_group)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def create_notification_tab(self) -> QWidget:
        """Create notification settings tab."""
        widget = QWidget()
        layout = QVBoxLayout()

        enabled_group = QGroupBox("Notification Settings")
        enabled_layout = QFormLayout()

        self.notification_min_burst_spin = QSpinBox()
        self.notification_min_burst_spin.setRange(1, 60)
        self.notification_min_burst_spin.setSuffix(" s")
        self.notification_min_burst_spin.setValue(10)
        enabled_layout.addRow(
            self._create_labeled_icon_widget(
                "Minimum burst duration for notification:",
                "Minimum typing session length to qualify for notifications.",
            ),
            self.notification_min_burst_spin,
        )

        self.notification_threshold_days_spin = QSpinBox()
        self.notification_threshold_days_spin.setRange(7, 365)
        self.notification_threshold_days_spin.setSuffix(" days")
        self.notification_threshold_days_spin.setValue(30)
        enabled_layout.addRow(
            self._create_labeled_icon_widget(
                "Threshold calculation lookback period:",
                "How many days of history to calculate thresholds from.",
            ),
            self.notification_threshold_days_spin,
        )

        self.notification_threshold_update_spin = QSpinBox()
        self.notification_threshold_update_spin.setRange(60, 3600)
        self.notification_threshold_update_spin.setSuffix(" s")
        self.notification_threshold_update_spin.setValue(300)
        enabled_layout.addRow(
            self._create_labeled_icon_widget(
                "Threshold update interval:",
                "How often to recalculate performance thresholds.",
            ),
            self.notification_threshold_update_spin,
        )

        enabled_group.setLayout(enabled_layout)
        layout.addWidget(enabled_group)

        time_group = QGroupBox("Daily Summary Time")
        time_layout = QFormLayout()

        self.daily_summary_enabled_check = QCheckBox("Enable daily summary")
        self.daily_summary_enabled_check.setChecked(True)
        self.daily_summary_enabled_check.setToolTip(
            "Show daily typing summary notification at configured time."
        )
        time_layout.addRow(self.daily_summary_enabled_check)

        self.notification_hour_spin = QSpinBox()
        self.notification_hour_spin.setRange(0, 23)
        self.notification_hour_spin.setSuffix(":00")
        self.notification_hour_spin.setValue(18)
        time_layout.addRow(
            self._create_labeled_icon_widget(
                "Hour:", "Time (24h) when daily typing summary is sent."
            ),
            self.notification_hour_spin,
        )

        time_group.setLayout(time_layout)
        layout.addWidget(time_group)

        # Worst letter notification settings
        worst_letter_group = QGroupBox("Hardest Letter Notifications")
        worst_letter_layout = QFormLayout()

        self.worst_letter_notification_check = QCheckBox("Notify on worst letter change")
        self.worst_letter_notification_check.setToolTip(
            "Send notification when your slowest letter key changes.\n"
            "Helps you track which letters need practice.\n"
            "Notifications are debounced (5 min minimum)."
        )
        worst_letter_layout.addRow(self.worst_letter_notification_check)

        self.worst_letter_debounce_spin = QSpinBox()
        self.worst_letter_debounce_spin.setRange(1, 60)
        self.worst_letter_debounce_spin.setSuffix(" min")
        self.worst_letter_debounce_spin.setValue(5)
        worst_letter_layout.addRow(
            self._create_labeled_icon_widget(
                "Hardest letter notification debounce:",
                "Minimum time between hardest letter change notifications.",
            ),
            self.worst_letter_debounce_spin,
        )

        worst_letter_group.setLayout(worst_letter_layout)
        layout.addWidget(worst_letter_group)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def create_data_tab(self) -> QWidget:
        """Create data management tab."""
        widget = QWidget()
        layout = QVBoxLayout()

        retention_group = QGroupBox("Data Retention")
        retention_layout = QFormLayout()

        self.retention_combo = QComboBox()
        self.retention_combo.addItem("Keep forever", -1)
        self.retention_combo.addItem("30 days", 30)
        self.retention_combo.addItem("60 days", 60)
        self.retention_combo.addItem("90 days", 90)
        self.retention_combo.addItem("180 days", 180)
        self.retention_combo.addItem("365 days", 365)
        retention_layout.addRow(
            self._create_labeled_icon_widget(
                "Keep data for:",
                "How long to keep typing history. 'Keep forever' never deletes data.",
            ),
            self.retention_combo,
        )

        retention_group.setLayout(retention_layout)
        layout.addWidget(retention_group)

        # Data Actions Group
        actions_group = QGroupBox("Data Actions")
        actions_layout = QHBoxLayout()

        export_btn = QPushButton("Export to CSV")
        export_btn.clicked.connect(self.export_csv)
        actions_layout.addWidget(export_btn)

        clear_btn = QPushButton("Clear All Data")
        clear_btn.clicked.connect(self.clear_data)
        actions_layout.addWidget(clear_btn)

        actions_layout.addStretch()
        actions_group.setLayout(actions_layout)
        layout.addWidget(actions_group)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def create_language_tab(self) -> QWidget:
        """Create language and dictionary settings tab."""
        widget = QWidget()
        layout = QVBoxLayout()

        # Dictionary Mode Group
        mode_group = QGroupBox("Dictionary Mode")
        mode_layout = QVBoxLayout()

        self.validate_mode_radio = QCheckBox("Validate words against dictionaries")
        self.validate_mode_radio.setToolTip(
            "Only store words found in selected dictionaries.\nBest for accurate word statistics."
        )
        self.validate_mode_radio.setChecked(True)

        mode_layout.addWidget(self.validate_mode_radio)
        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)

        # Add info label about ignore words file
        ignore_info_label = QLabel()
        ignore_info_label.setWordWrap(True)
        ignore_info_label.setStyleSheet("color: #666; font-style: italic; font-size: 11px;")
        ignore_info_label.setText(
            "To ignore specific words, add them (one per line) to:\n"
            f"{Path.home() / '.config' / 'realtypecoach' / 'ignorewords.txt'}"
        )
        ignore_info_label.setToolTip(
            "Words listed in ignorewords.txt will be excluded from statistics.\n"
            "Add one word per line. Lines starting with # are treated as comments.\n\n"
            "Changes take effect on next application start."
        )
        layout.addWidget(ignore_info_label)

        # Language Selection Group
        lang_group = QGroupBox("Active Languages")
        lang_layout = QVBoxLayout()

        lang_label_container = self._create_labeled_icon_widget(
            "Select languages to validate:",
            "Choose which dictionaries to use for word validation.\n"
            "Only words found in these dictionaries will be tracked.",
        )
        lang_layout.addWidget(lang_label_container)

        self.language_list_widget = QListWidget()
        self.language_list_widget.setMaximumHeight(120)
        lang_layout.addWidget(self.language_list_widget)

        # Scan button
        scan_button_layout = QHBoxLayout()
        self.rescan_button = QPushButton("Rescan Dictionaries")
        self.rescan_button.clicked.connect(self.rescan_dictionaries)
        self.rescan_button.setToolTip(
            "Search the system for available Hunspell dictionaries.\n"
            "Use this after installing new dictionaries."
        )
        scan_button_layout.addWidget(self.rescan_button)
        scan_button_layout.addStretch()
        lang_layout.addLayout(scan_button_layout)

        lang_group.setLayout(lang_layout)
        layout.addWidget(lang_group)

        # Status label
        self.dictionary_status_label = QLabel()
        self.dictionary_status_label.setWordWrap(True)
        self.dictionary_status_label.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(self.dictionary_status_label)

        layout.addStretch()
        widget.setLayout(layout)

        # Trigger initial scan
        self.rescan_dictionaries()

        return widget

    def create_database_tab(self) -> QWidget:
        """Create database settings tab."""
        widget = QWidget()
        layout = QVBoxLayout()

        # Backend selection
        backend_group = QGroupBox("Database Backend")
        backend_layout = QFormLayout()

        self.backend_combo = QComboBox()
        self.backend_combo.addItem("SQLite (Local Only)", "sqlite")
        self.backend_combo.addItem("PostgreSQL (Remote)", "postgres")
        backend_layout.addRow(
            self._create_labeled_icon_widget(
                "Database backend:",
                "Select the database backend:\n"
                "• SQLite (Local Only): Default, encrypted local database\n"
                "• PostgreSQL (Remote): Remote database on VPS for multi-device sync",
            ),
            self.backend_combo,
        )
        backend_group.setLayout(backend_layout)
        layout.addWidget(backend_group)

        # PostgreSQL connection settings
        postgres_group = QGroupBox("PostgreSQL Connection")
        postgres_layout = QFormLayout()

        self.postgres_host_edit = ""
        self.postgres_host_input = QLineEdit()
        self.postgres_host_input.setPlaceholderText("localhost")
        postgres_layout.addRow(
            self._create_labeled_icon_widget(
                "Host:",
                "PostgreSQL server hostname or IP address",
            ),
            self.postgres_host_input,
        )

        self.postgres_port_spin = QSpinBox()
        self.postgres_port_spin.setRange(1, 65535)
        self.postgres_port_spin.setValue(5432)
        postgres_layout.addRow(
            self._create_labeled_icon_widget(
                "Port:",
                "PostgreSQL server port (default: 5432)",
            ),
            self.postgres_port_spin,
        )

        self.postgres_database_input = QLineEdit()
        self.postgres_database_input.setPlaceholderText("realtypecoach")
        postgres_layout.addRow(
            self._create_labeled_icon_widget(
                "Database:",
                "PostgreSQL database name",
            ),
            self.postgres_database_input,
        )

        self.postgres_user_input = QLineEdit()
        self.postgres_user_input.setPlaceholderText("realtypecoach")
        postgres_layout.addRow(
            self._create_labeled_icon_widget(
                "User:",
                "PostgreSQL username",
            ),
            self.postgres_user_input,
        )

        password_container = QWidget()
        password_layout = QHBoxLayout(password_container)
        password_layout.setContentsMargins(0, 0, 0, 0)
        self.postgres_password_input = QLineEdit()
        self.postgres_password_input.setEchoMode(QLineEdit.Password)
        self.postgres_password_input.setPlaceholderText("Stored in keyring")
        self.postgres_password_input.setText("••••••••")
        self.postgres_password_input.setReadOnly(True)
        password_layout.addWidget(self.postgres_password_input)

        set_password_btn = QPushButton("Set Password")
        set_password_btn.clicked.connect(self.set_postgres_password)
        password_layout.addWidget(set_password_btn)

        postgres_layout.addRow(
            self._create_labeled_icon_widget(
                "Password:",
                "PostgreSQL password (stored securely in system keyring)",
            ),
            password_container,
        )

        self.sslmode_combo = QComboBox()
        self.sslmode_combo.addItem("Require", "require")
        self.sslmode_combo.addItem("Verify Full", "verify-full")
        self.sslmode_combo.addItem("Prefer", "prefer")
        self.sslmode_combo.addItem("Allow", "allow")
        self.sslmode_combo.addItem("Disable", "disable")
        postgres_layout.addRow(
            self._create_labeled_icon_widget(
                "SSL mode:",
                "SSL/TLS encryption mode:\n"
                "• Require: Always encrypted (recommended)\n"
                "• Verify Full: Encrypted + certificate verification\n"
                "• Prefer: Use SSL if available\n"
                "• Allow: Use SSL if server requests it\n"
                "• Disable: No encryption (not recommended)",
            ),
            self.sslmode_combo,
        )

        postgres_group.setLayout(postgres_layout)
        layout.addWidget(postgres_group)

        # Test connection button
        test_conn_layout = QHBoxLayout()
        test_conn_layout.addStretch()
        self.test_conn_btn = QPushButton("Test Connection")
        self.test_conn_btn.clicked.connect(self.test_postgres_connection)
        test_conn_layout.addWidget(self.test_conn_btn)
        layout.addLayout(test_conn_layout)

        # Connection status label
        self.conn_status_label = QLabel()
        self.conn_status_label.setWordWrap(True)
        self.conn_status_label.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(self.conn_status_label)

        # User Identity Group
        user_group = QGroupBox("User Identity")
        user_layout = QFormLayout()

        self.user_id_label = QLabel("Not set")
        self.user_id_label.setStyleSheet("font-family: monospace; font-size: 10px;")
        user_layout.addRow(
            self._create_labeled_icon_widget(
                "User ID:",
                "Your unique user identifier for multi-device sync.\n"
                "This ID is automatically generated on first launch.",
            ),
            self.user_id_label,
        )

        username_container = QWidget()
        username_layout_layout = QHBoxLayout(username_container)
        username_layout_layout.setContentsMargins(0, 0, 0, 0)
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("Auto-generated username")
        username_layout_layout.addWidget(self.username_edit)

        update_username_btn = QPushButton("Update")
        update_username_btn.setMaximumWidth(80)
        update_username_btn.clicked.connect(self.update_username)
        username_layout_layout.addWidget(update_username_btn)

        user_layout.addRow(
            self._create_labeled_icon_widget(
                "Username:",
                "Customizable username for identification.\n"
                "Auto-generated as hostname_random on first launch.",
            ),
            username_container,
        )

        # Encryption key export/import
        key_buttons_layout = QHBoxLayout()
        self.export_key_btn = QPushButton("Export Encryption Key")
        self.export_key_btn.clicked.connect(self.export_encryption_key)
        key_buttons_layout.addWidget(self.export_key_btn)

        self.import_key_btn = QPushButton("Import Encryption Key")
        self.import_key_btn.clicked.connect(self.import_encryption_key)
        key_buttons_layout.addWidget(self.import_key_btn)

        user_layout.addRow("", key_buttons_layout)

        user_group.setLayout(user_layout)
        layout.addWidget(user_group)

        # Sync Group
        sync_group = QGroupBox("Data Sync")
        sync_layout = QVBoxLayout()

        self.upload_history_btn = QPushButton("Upload/Download Typing History")
        self.upload_history_btn.clicked.connect(self.upload_history_to_database)
        sync_layout.addWidget(self.upload_history_btn)

        self.last_sync_label = QLabel("Never synced")
        self.last_sync_label.setStyleSheet("color: #666; font-style: italic;")
        sync_layout.addWidget(self.last_sync_label)

        sync_group.setLayout(sync_layout)
        layout.addWidget(sync_group)

        # Auto-sync settings group
        auto_sync_group = QGroupBox("Automatic Background Sync")
        auto_sync_layout = QFormLayout()

        self.auto_sync_enabled_check = QCheckBox("Enable automatic sync")
        self.auto_sync_enabled_check.setToolTip(
            "Automatically sync with remote database in the background"
        )
        auto_sync_layout.addRow("", self.auto_sync_enabled_check)

        self.sync_interval_spin = QSpinBox()
        self.sync_interval_spin.setRange(60, 86400)  # 1 minute to 24 hours
        self.sync_interval_spin.setValue(300)
        self.sync_interval_spin.setSuffix(" seconds")
        self.sync_interval_spin.setToolTip("How often to sync with remote database")
        auto_sync_layout.addRow("Sync interval:", self.sync_interval_spin)

        # Status label showing next sync time
        self.next_sync_label = QLabel("Auto-sync disabled")
        self.next_sync_label.setStyleSheet("color: #666; font-style: italic;")
        auto_sync_layout.addRow("", self.next_sync_label)

        auto_sync_group.setLayout(auto_sync_layout)
        layout.addWidget(auto_sync_group)

        layout.addStretch()
        widget.setLayout(layout)

        # Connect backend combo to enable/disable postgres settings
        self.backend_combo.currentIndexChanged.connect(self.on_backend_changed)

        return widget

    def on_backend_changed(self) -> None:
        """Handle backend selection change."""
        backend = self.backend_combo.currentData()
        is_postgres = backend == "postgres"

        # Enable/disable postgres settings based on backend selection
        postgres_widgets = [
            self.postgres_host_input,
            self.postgres_port_spin,
            self.postgres_database_input,
            self.postgres_user_input,
            self.postgres_password_input,
            self.sslmode_combo,
            self.test_conn_btn,
        ]

        for widget in postgres_widgets:
            widget.setEnabled(is_postgres)

        # Enable/disable user identity and sync widgets
        user_sync_widgets = [
            self.user_id_label,
            self.username_edit,
            self.export_key_btn,
            self.import_key_btn,
            self.upload_history_btn,
        ]

        for widget in user_sync_widgets:
            widget.setEnabled(is_postgres)

        # Enable/disable auto-sync widgets (only when postgres is selected)
        auto_sync_widgets = [
            self.auto_sync_enabled_check,
            self.sync_interval_spin,
        ]

        for widget in auto_sync_widgets:
            widget.setEnabled(is_postgres)

    def set_postgres_password(self) -> None:
        """Set PostgreSQL password in keyring."""
        from utils.crypto import CryptoManager

        # Get current database path
        db_path = Path.home() / ".local" / "share" / "realtypecoach" / "typing_data.db"
        crypto = CryptoManager(db_path)

        # Get password from user
        password, ok = QInputDialog.getText(
            self,
            "Set PostgreSQL Password",
            "Enter PostgreSQL password:",
            QLineEdit.Password,
        )

        if ok and password:
            try:
                crypto.store_postgres_password(password)
                self.postgres_password_input.setText("••••••••")
                self.conn_status_label.setText("Password saved to keyring.")
                self.conn_status_label.setStyleSheet("color: green; font-style: italic;")
            except Exception as e:
                self.conn_status_label.setText(f"Error saving password: {e}")
                self.conn_status_label.setStyleSheet("color: red; font-style: italic;")

    def test_postgres_connection(self) -> None:
        """Test PostgreSQL connection."""
        try:
            import psycopg2
        except ImportError:
            self.conn_status_label.setText(
                "psycopg2 not installed. Install with: pip install psycopg2-binary"
            )
            self.conn_status_label.setStyleSheet("color: red; font-style: italic;")
            return

        # Get password from keyring
        db_path = Path.home() / ".local" / "share" / "realtypecoach" / "typing_data.db"
        from utils.crypto import CryptoManager

        crypto = CryptoManager(db_path)
        password = crypto.get_postgres_password()

        if not password:
            self.conn_status_label.setText("No password set. Please set password first.")
            self.conn_status_label.setStyleSheet("color: red; font-style: italic;")
            return

        # Get connection parameters
        host = self.postgres_host_input.text().strip()
        port = self.postgres_port_spin.value()
        database = self.postgres_database_input.text().strip() or "realtypecoach"
        user = self.postgres_user_input.text().strip()
        sslmode = self.sslmode_combo.currentData()

        if not all([host, user]):
            self.conn_status_label.setText("Please fill in host and user fields.")
            self.conn_status_label.setStyleSheet("color: red; font-style: italic;")
            return

        # Test connection
        self.conn_status_label.setText("Testing connection...")
        self.conn_status_label.setStyleSheet("color: #666; font-style: italic;")
        QApplication.processEvents()

        try:
            conn = psycopg2.connect(
                host=host,
                port=port,
                database=database,
                user=user,
                password=password,
                sslmode=sslmode,
                connect_timeout=10,
            )
            cursor = conn.cursor()
            cursor.execute("SELECT version()")
            version = cursor.fetchone()[0]
            cursor.close()
            conn.close()

            self.conn_status_label.setText(
                f"Connection successful!\nPostgreSQL version: {version[:50]}..."
            )
            self.conn_status_label.setStyleSheet("color: green; font-style: italic;")
        except Exception as e:
            self.conn_status_label.setText(f"Connection failed: {str(e)}")
            self.conn_status_label.setStyleSheet("color: red; font-style: italic;")

    def _update_detected_layout(self) -> None:
        """Update the detected keyboard layout hint."""
        try:
            from utils.keyboard_detector import get_current_layout

            detected_layout = get_current_layout()
            layout_names = {
                "us": "US (QWERTY)",
                "de": "German (QWERTZ)",
            }
            layout_name = layout_names.get(detected_layout, detected_layout.upper())
            self.detected_layout_label.setText(f"Detected: {layout_name}")
        except Exception as e:
            log.debug(f"Could not detect keyboard layout: {e}")
            self.detected_layout_label.setText("Detected: Unknown")

    def rescan_dictionaries(self) -> None:
        """Rescan system for available dictionaries."""
        try:
            from utils.dict_detector import DictionaryDetector

            # Preserve current UI selections before clearing
            current_ui_selections = set()
            for i in range(self.language_list_widget.count()):
                item = self.language_list_widget.item(i)
                if item.checkState() == Qt.Checked:
                    path = item.data(Qt.UserRole)
                    if path:
                        current_ui_selections.add(path)

            available = DictionaryDetector.detect_available()

            # Enable checkbox selection
            self.language_list_widget.clear()
            self.language_list_widget.setSelectionMode(QListWidget.NoSelection)

            # Prioritize UI selections over settings (for rescanning while dialog is open)
            enabled_dicts_setting = self.current_settings.get("enabled_dictionaries", "")
            log.info(
                f"rescan: self.current_settings.get('enabled_dictionaries', '') returned: {enabled_dicts_setting!r}"
            )
            if current_ui_selections:
                selected_set = current_ui_selections
                log.info(f"rescan: using current UI selections: {selected_set}")
            elif enabled_dicts_setting and enabled_dicts_setting.strip():
                selected_set = set(p.strip() for p in enabled_dicts_setting.split(",") if p.strip())
                log.info(
                    f"rescan: loaded {len(selected_set)} dictionaries from settings: {selected_set}"
                )
            else:
                selected_set = set()
                log.info(
                    "rescan: using default selections (enabled_dicts_setting is empty or whitespace-only)"
                )

            for dict_info in available:
                item_text = f"{dict_info.language_name}"
                if dict_info.variant:
                    item_text += f" ({dict_info.variant})"

                # Create item with checkbox
                from PySide6.QtWidgets import QListWidgetItem

                item = QListWidgetItem(item_text)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Unchecked)

                # Store dict_info path as data for identification
                item.setData(Qt.UserRole, dict_info.path)

                # Set default selections: German (reform) and US English
                # Or restore from saved settings
                should_check = False
                if selected_set:
                    # Restore from settings
                    if dict_info.path in selected_set:
                        should_check = True
                        log.info(f"Checking {dict_info.path} (matched saved selection)")
                    else:
                        log.debug(f"Not checking {dict_info.path} (not in selected_set)")
                else:
                    # Default selections
                    if (
                        dict_info.language_code == "de"
                        and dict_info.variant
                        and "reform" in dict_info.variant
                        and "pre-reform" not in dict_info.variant
                    ):
                        should_check = True
                        log.info(f"Checking {dict_info.path} (default German reform)")
                    elif (
                        dict_info.language_code == "en"
                        and dict_info.variant
                        and "American" in dict_info.variant
                    ):
                        should_check = True
                        log.info(f"Checking {dict_info.path} (default American English)")

                if should_check:
                    item.setCheckState(Qt.Checked)

                self.language_list_widget.addItem(item)

            # Update status label
            available_count = sum(1 for d in available if d.available)
            if available_count > 0:
                self.dictionary_status_label.setText(
                    f"Found {available_count} available dictionaries"
                )
            else:
                self.dictionary_status_label.setText(
                    "No dictionaries found - accept-all mode will be enabled automatically"
                )
        except (ImportError, AttributeError, OSError) as e:
            log.error(f"Error scanning dictionaries: {e}")
            self.dictionary_status_label.setText(f"Error scanning dictionaries: {e}")
            self.language_list_widget.clear()

    def get_enabled_languages(self) -> list:
        """Get list of enabled dictionary paths based on user selection."""
        enabled_paths = []
        for i in range(self.language_list_widget.count()):
            item = self.language_list_widget.item(i)
            if item.checkState() == Qt.Checked:
                path = item.data(Qt.UserRole)
                if path:
                    enabled_paths.append(path)

        return enabled_paths

    def load_current_settings(self) -> None:
        """Load current settings into UI."""
        self.burst_timeout_spin.setValue(self.current_settings.get("burst_timeout_ms", 1000))
        self.word_boundary_timeout_spin.setValue(
            self.current_settings.get("word_boundary_timeout_ms", 1000)
        )

        # Load duration calculation method
        duration_method = self.current_settings.get("burst_duration_calculation", "total_time")
        index = self.duration_method_combo.findData(duration_method)
        if index >= 0:
            self.duration_method_combo.setCurrentIndex(index)

        self.active_threshold_spin.setValue(
            self.current_settings.get("active_time_threshold_ms", 500)
        )

        self.high_score_duration_spin.setValue(
            self.current_settings.get("high_score_min_duration_ms", 5000)
        )
        self.min_key_count_spin.setValue(self.current_settings.get("min_burst_key_count", 10))
        self.min_burst_duration_spin.setValue(
            self.current_settings.get("min_burst_duration_ms", 5000)
        )
        self.keyboard_layout_combo.setCurrentText(
            self.current_settings.get("keyboard_layout", "Auto-detect").capitalize()
        )
        self.stats_update_interval_spin.setValue(
            self.current_settings.get("stats_update_interval_sec", 2)
        )
        self.notification_min_burst_spin.setValue(
            self.current_settings.get("notification_min_burst_ms", 10000) // 1000
        )
        self.notification_threshold_days_spin.setValue(
            self.current_settings.get("notification_threshold_days", 30)
        )
        self.notification_threshold_update_spin.setValue(
            self.current_settings.get("notification_threshold_update_sec", 300)
        )
        self.notification_hour_spin.setValue(
            self.current_settings.get("notification_time_hour", 18)
        )
        self.daily_summary_enabled_check.setChecked(
            self.current_settings.get("daily_summary_enabled", True)
        )
        self.worst_letter_notification_check.setChecked(
            self.current_settings.get("worst_letter_notifications_enabled", False)
        )
        self.worst_letter_debounce_spin.setValue(
            self.current_settings.get("worst_letter_notification_debounce_min", 5)
        )
        retention_days = self.current_settings.get("data_retention_days", -1)
        index = self.retention_combo.findData(retention_days)
        if index >= 0:
            self.retention_combo.setCurrentIndex(index)

        # Load dictionary mode
        dict_mode = self.current_settings.get("dictionary_mode", "validate")
        self.validate_mode_radio.setChecked(dict_mode == "validate")

        # Load database settings
        database_backend = self.current_settings.get("database_backend", "sqlite")
        index = self.backend_combo.findData(database_backend)
        if index >= 0:
            self.backend_combo.setCurrentIndex(index)

        self.postgres_host_input.setText(self.current_settings.get("postgres_host", ""))
        self.postgres_port_spin.setValue(self.current_settings.get("postgres_port", 5432))
        self.postgres_database_input.setText(
            self.current_settings.get("postgres_database", "realtypecoach")
        )
        self.postgres_user_input.setText(self.current_settings.get("postgres_user", ""))
        sslmode = self.current_settings.get("postgres_sslmode", "require")
        index = self.sslmode_combo.findData(sslmode)
        if index >= 0:
            self.sslmode_combo.setCurrentIndex(index)

        # Load user identity information
        self._update_user_display()
        self._update_last_sync_label()

        # Load auto-sync settings
        self.auto_sync_enabled_check.setChecked(
            self.current_settings.get("auto_sync_enabled", False)
        )
        self.sync_interval_spin.setValue(
            self.current_settings.get("auto_sync_interval_sec", 300)
        )

        # Update next sync status
        self._update_next_sync_label()

        # Trigger backend changed to enable/disable postgres settings
        self.on_backend_changed()

    def get_settings(self) -> dict[str, Any]:
        """Get settings from UI.

        Returns:
            Dictionary of setting key-value pairs
        """
        # Get enabled dictionary paths
        enabled_dict_paths = self.get_enabled_languages()
        enabled_dicts_str = ",".join(enabled_dict_paths) if enabled_dict_paths else ""
        log.debug(
            f"get_settings: enabled_dict_paths={enabled_dict_paths}, enabled_dicts_str={enabled_dicts_str!r}"
        )

        # Also update enabled_languages for backward compatibility
        from utils.dict_detector import DictionaryDetector

        enabled_lang_codes = set()
        for path in enabled_dict_paths:
            dict_info = DictionaryDetector.identify_dictionary(path)
            if dict_info:
                enabled_lang_codes.add(dict_info.language_code)
        enabled_langs_str = ",".join(sorted(enabled_lang_codes)) if enabled_lang_codes else "en,de"

        return {
            "burst_timeout_ms": str(self.burst_timeout_spin.value()),
            "word_boundary_timeout_ms": str(self.word_boundary_timeout_spin.value()),
            "burst_duration_calculation": self.duration_method_combo.currentData(),
            "active_time_threshold_ms": str(self.active_threshold_spin.value()),
            "high_score_min_duration_ms": str(self.high_score_duration_spin.value()),
            "min_burst_key_count": str(self.min_key_count_spin.value()),
            "min_burst_duration_ms": str(self.min_burst_duration_spin.value()),
            "keyboard_layout": self.keyboard_layout_combo.currentData().lower(),
            "stats_update_interval_sec": str(self.stats_update_interval_spin.value()),
            "notification_min_burst_ms": str(self.notification_min_burst_spin.value() * 1000),
            "notification_threshold_days": str(self.notification_threshold_days_spin.value()),
            "notification_threshold_update_sec": str(
                self.notification_threshold_update_spin.value()
            ),
            "notification_time_hour": str(self.notification_hour_spin.value()),
            "daily_summary_enabled": str(self.daily_summary_enabled_check.isChecked()),
            "worst_letter_notifications_enabled": str(
                self.worst_letter_notification_check.isChecked()
            ),
            "worst_letter_notification_debounce_min": str(self.worst_letter_debounce_spin.value()),
            "data_retention_days": str(self.retention_combo.currentData()),
            "dictionary_mode": "validate" if self.validate_mode_radio.isChecked() else "accept_all",
            "enabled_languages": enabled_langs_str,
            "enabled_dictionaries": enabled_dicts_str,
            # Database settings
            "database_backend": self.backend_combo.currentData(),
            "postgres_host": self.postgres_host_input.text(),
            "postgres_port": str(self.postgres_port_spin.value()),
            "postgres_database": self.postgres_database_input.text() or "realtypecoach",
            "postgres_user": self.postgres_user_input.text(),
            "postgres_sslmode": self.sslmode_combo.currentData(),
            # Auto-sync settings
            "auto_sync_enabled": str(self.auto_sync_enabled_check.isChecked()),
            "auto_sync_interval_sec": str(self.sync_interval_spin.value()),
        }

    def accept(self) -> None:
        """Validate and accept the dialog."""
        # Check if postgres backend is selected
        if self.backend_combo.currentData() in ("postgres", "hybrid"):
            host = self.postgres_host_input.text().strip()
            user = self.postgres_user_input.text().strip()

            if not host:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self,
                    "Incomplete PostgreSQL Settings",
                    "PostgreSQL host is required when using PostgreSQL backend.\n\n"
                    "Please fill in the host field or switch back to SQLite."
                )
                self.postgres_host_input.setFocus()
                return

            if not user:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self,
                    "Incomplete PostgreSQL Settings",
                    "PostgreSQL user is required when using PostgreSQL backend.\n\n"
                    "Please fill in the user field or switch back to SQLite."
                )
                self.postgres_user_input.setFocus()
                return

        super().accept()

    def export_csv(self) -> None:
        """Export data to CSV file."""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Typing Data", "", "CSV Files (*.csv);;All Files (*)"
        )

        if file_path:
            self.settings = self.get_settings()
            self.accept()

    def clear_data(self) -> None:
        """Clear all stored data."""
        from PySide6.QtWidgets import QMessageBox

        msg_box = QMessageBox(
            QMessageBox.Question,
            "Clear All Data",
            "Are you sure you want to delete all typing data?\n\nThis action cannot be undone!",
            QMessageBox.Yes | QMessageBox.No,
            self,
        )
        msg_box.setDefaultButton(QMessageBox.No)

        # Make button icons visible on dark backgrounds
        msg_box.setStyleSheet(
            """
            QMessageBox { messagebox-text-interaction-flags: 5; }
            QPushButton {
                color: palette(text);
            }
            QPushButton[qstyleclass="pushbutton"] {
                color: palette(text);
            }
        """
        )
        # Apply text color to icons
        for button in msg_box.findChildren(QPushButton):
            icon = button.icon()
            if not icon.isNull():
                # Create a colored pixmap from the icon
                pixmap = icon.pixmap(button.iconSize())
                painter = QPainter(pixmap)
                painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
                painter.fillRect(pixmap.rect(), button.palette().color(QPalette.ButtonText))
                painter.end()
                button.setIcon(QIcon(pixmap))

        reply = msg_box.exec()

        if reply == QMessageBox.Yes:
            self.settings = self.get_settings()
            self.settings["__clear_database__"] = True
            self.accept()

    # ========== User Identity and Sync Handlers ==========

    def update_username(self) -> None:
        """Update username for current user."""
        from core.user_manager import UserManager
        from PySide6.QtWidgets import QMessageBox

        new_username = self.username_edit.text().strip()
        if not new_username:
            QMessageBox.warning(self, "Invalid Username", "Username cannot be empty.")
            return

        try:
            db_path = Path.home() / ".local" / "share" / "realtypecoach" / "typing_data.db"
            # We need to create a Config instance here
            from utils.config import Config
            config = Config(db_path)
            user_manager = UserManager(db_path, config)
            user_manager.update_username(new_username)
            self.user_id_label.setText(f"Username updated to: {new_username}")
        except Exception as e:
            QMessageBox.critical(self, "Update Failed", f"Failed to update username:\n{e}")

    def export_encryption_key(self) -> None:
        """Show encryption key for copying to another device."""
        from core.user_manager import UserManager
        from PySide6.QtWidgets import QMessageBox, QTextEdit

        db_path = Path.home() / ".local" / "share" / "realtypecoach" / "typing_data.db"
        from utils.config import Config
        config = Config(db_path)

        try:
            user_manager = UserManager(db_path, config)
            user = user_manager.get_or_create_current_user()

            # Format: base64(user_id + 32-byte key)
            key_data = user_manager.export_encryption_key()

            dialog = QDialog(self)
            dialog.setWindowTitle("Export Encryption Key")
            dialog.setMinimumWidth(500)

            layout = QVBoxLayout()
            info_label = QLabel(
                "Your encryption key. Copy this to use RealTypeCoach on another device:\n\n"
                "⚠️ Keep this key secret! Anyone with this key can decrypt your typing data."
            )
            info_label.setWordWrap(True)

            key_display = QTextEdit()
            key_display.setReadOnly(True)
            key_display.setText(key_data)
            key_display.setFixedHeight(80)

            copy_btn = QPushButton("Copy to Clipboard")
            copy_btn.clicked.connect(lambda: self._copy_key_to_clipboard(key_data, dialog))

            layout.addWidget(info_label)
            layout.addWidget(key_display)
            layout.addWidget(copy_btn)

            dialog.setLayout(layout)
            dialog.exec()

        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Failed to export encryption key:\n{e}")

    def import_encryption_key(self) -> None:
        """Import encryption key from another device."""
        from core.user_manager import UserManager
        from PySide6.QtWidgets import QMessageBox, QTextEdit

        db_path = Path.home() / ".local" / "share" / "realtypecoach" / "typing_data.db"
        from utils.config import Config
        config = Config(db_path)

        dialog = QDialog(self)
        dialog.setWindowTitle("Import Encryption Key")
        dialog.setMinimumWidth(500)

        layout = QVBoxLayout()
        warning_label = QLabel(
            "⚠️ This will overwrite your current encryption key!\n"
            "Existing encrypted data will become inaccessible.\n\n"
            "Paste the key from another device:"
        )
        warning_label.setWordWrap(True)

        key_input = QTextEdit()
        key_input.setPlaceholderText("Paste encryption key here...")

        buttons = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        import_btn = QPushButton("Import Key")
        import_btn.setStyleSheet("background-color: #d32f2f; color: white;")
        import_btn.clicked.connect(lambda: self._do_import_key(key_input.toPlainText(), dialog, db_path, config))

        buttons.addWidget(cancel_btn)
        buttons.addWidget(import_btn)

        layout.addWidget(warning_label)
        layout.addWidget(key_input)
        layout.addLayout(buttons)

        dialog.setLayout(layout)
        dialog.exec()

    def _copy_key_to_clipboard(self, key_data: str, dialog: QDialog) -> None:
        """Copy encryption key to clipboard."""
        from PySide6.QtWidgets import QApplication

        clipboard = QApplication.clipboard()
        clipboard.setText(key_data)
        # Brief feedback
        original_text = key_data
        dialog.findChild(QTextEdit, None).setPlainText("✓ Copied to clipboard!")
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1000, lambda: dialog.findChild(QTextEdit, None).setPlainText(original_text))

    def _do_import_key(self, key_data: str, dialog: QDialog, db_path: Path, config) -> None:
        """Actually import the key after validation."""
        from core.user_manager import UserManager
        from PySide6.QtWidgets import QMessageBox

        try:
            user_manager = UserManager(db_path, config)
            user = user_manager.import_encryption_key(key_data.strip())
            QMessageBox.information(
                dialog,
                "Import Successful",
                f"Encryption key imported for user:\n{user.username}\n\n"
                f"You can now sync data from this device.",
            )
            dialog.accept()
            self._update_user_display()
        except ValueError as e:
            QMessageBox.critical(
                dialog,
                "Import Failed",
                f"Invalid encryption key: {e}",
            )
        except Exception as e:
            QMessageBox.critical(
                dialog,
                "Import Failed",
                f"Failed to import encryption key: {e}",
            )

    def upload_history_to_database(self) -> None:
        """Manual merge/sync button handler."""
        from PySide6.QtWidgets import QMessageBox, QPushButton

        # Check if we have access to storage
        if self.storage is None:
            QMessageBox.warning(
                self,
                "Storage Not Available",
                "Storage instance not available. Please restart the application and try again."
            )
            return

        # Check if PostgreSQL is configured
        if self.backend_combo.currentData() != "postgres":
            QMessageBox.warning(
                self,
                "Not Configured",
                "Please select 'PostgreSQL (Remote)' as the database backend first."
            )
            return

        host = self.postgres_host_input.text().strip()
        postgres_user = self.postgres_user_input.text().strip()

        if not all([host, postgres_user]):
            QMessageBox.warning(self, "Not Configured", "Please configure PostgreSQL connection first.")
            return

        # Store current button state
        self.upload_history_btn.setEnabled(False)
        self.upload_history_btn.setText("Syncing...")

        # Update status label to show sync in progress
        self.last_sync_label.setText("⏳ Syncing...")
        self.last_sync_label.setStyleSheet("color: #007acc; font-style: italic;")

        # Process events to update UI
        QApplication.processEvents()

        try:
            # Use storage's merge_with_remote method which has the proper fix
            result = self.storage.merge_with_remote()

            if result["success"]:
                total_records = result["pushed"] + result["pulled"]
                self.last_sync_label.setText(f"✓ Last sync: Just now ({total_records} records)")
                self.last_sync_label.setStyleSheet("color: green; font-style: italic;")

                QMessageBox.information(
                    self,
                    "Sync Complete",
                    f"Sync completed successfully!\n\n"
                    f"Pushed: {result['pushed']} records\n"
                    f"Pulled: {result['pulled']} records\n"
                    f"Conflicts resolved: {result['conflicts_resolved']}\n"
                    f"Duration: {result['duration_ms']} ms"
                )
            else:
                self.last_sync_label.setText("✗ Sync failed - check logs")
                self.last_sync_label.setStyleSheet("color: red; font-style: italic;")
                QMessageBox.critical(
                    self,
                    "Sync Failed",
                    f"Sync failed:\n{result.get('error', 'Unknown error')}"
                )

        except Exception as e:
            self.last_sync_label.setText("✗ Sync failed - check logs")
            self.last_sync_label.setStyleSheet("color: red; font-style: italic;")
            QMessageBox.critical(self, "Sync Failed", f"Error during sync:\n{e}")
        finally:
            # Always restore button state
            self.upload_history_btn.setEnabled(True)
            self.upload_history_btn.setText("Upload/Download Typing History")

    def _update_user_display(self) -> None:
        """Update user identity display."""
        from core.user_manager import UserManager

        db_path = Path.home() / ".local" / "share" / "realtypecoach" / "typing_data.db"
        from utils.config import Config
        config = Config(db_path)

        try:
            user_manager = UserManager(db_path, config)
            user = user_manager.get_or_create_current_user()
            self.user_id_label.setText(user.user_id)
            self.username_edit.setText(user.username)
        except Exception:
            self.user_id_label.setText("Not set")
            self.username_edit.setText("")

    def _update_last_sync_label(self) -> None:
        """Update last sync time display."""
        from utils.config import Config

        db_path = Path.home() / ".local" / "share" / "realtypecoach" / "typing_data.db"
        config = Config(db_path)

        last_sync = config.get_int("last_sync_timestamp")
        if last_sync:
            from datetime import datetime
            sync_time = datetime.fromtimestamp(last_sync / 1000).strftime("%Y-%m-%d %H:%M:%S")
            self.last_sync_label.setText(f"Last sync: {sync_time}")
        else:
            self.last_sync_label.setText("Never synced")

    def _update_next_sync_label(self) -> None:
        """Update next sync status label."""
        if not self.sync_handler:
            return

        if not self.auto_sync_enabled_check.isChecked():
            self.next_sync_label.setText("Auto-sync disabled")
            self.next_sync_label.setStyleSheet("color: #666; font-style: italic;")
            return

        # Check if backend is postgres
        if self.backend_combo.currentData() != "postgres":
            self.next_sync_label.setText("Auto-sync requires PostgreSQL backend")
            self.next_sync_label.setStyleSheet("color: #f57900; font-style: italic;")
            return

        interval = self.sync_interval_spin.value()
        if self.sync_handler.running:
            self.next_sync_label.setText(
                f"Auto-sync active (every {interval} seconds)"
            )
            self.next_sync_label.setStyleSheet("color: green; font-style: italic;")
        else:
            self.next_sync_label.setText(
                f"Auto-sync configured (every {interval} seconds)"
            )
            self.next_sync_label.setStyleSheet("color: #666; font-style: italic;")

    def _on_sync_completed(self, result: dict) -> None:
        """Handle sync completion from sync handler.

        Args:
            result: Sync result dictionary
        """
        self._update_last_sync_label()
        if self.auto_sync_enabled_check.isChecked():
            self._update_next_sync_label()
