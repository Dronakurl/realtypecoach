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
    QTextEdit,
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
        # Track Ollama availability
        self.ollama_available = False
        # Internal storage for available models (property setter refreshes the dropdown)
        self._available_models_internal: list[str] = []
        # Set window flags for Wayland compatibility
        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        self.init_ui()
        self.load_current_settings()
        # Connect sync signals after UI is initialized
        self._connect_sync_signals()

    @property
    def _available_models(self) -> list[str]:
        """Get available Ollama models."""
        return self._available_models_internal

    @_available_models.setter
    def _available_models(self, models: list[str]) -> None:
        """Set available Ollama models and refresh dropdown.

        Args:
            models: List of available model names
        """
        self._available_models_internal = models
        # Refresh the dropdown after a delay to ensure UI is fully initialized
        if hasattr(self, "llm_model_combo") and self.ollama_available:
            QTimer.singleShot(0, self._refresh_llm_models)

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

        language_tab = self.create_language_tab()
        tabs.addTab(language_tab, "Language")
        tabs.setTabIcon(2, self._create_palette_aware_icon("accessories-dictionary"))

        database_tab = self.create_database_tab()
        tabs.addTab(database_tab, "Database")
        tabs.setTabIcon(3, self._create_palette_aware_icon("network-server"))

        llm_tab = self.create_llm_tab()
        tabs.addTab(llm_tab, "LLM")
        tabs.setTabIcon(4, self._create_palette_aware_icon("text-x-script"))

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

        # Data Management Group (moved from Data tab)
        data_group = QGroupBox("Data Management")
        data_layout = QFormLayout()

        self.retention_combo = QComboBox()
        self.retention_combo.addItem("Keep forever", -1)
        self.retention_combo.addItem("30 days", 30)
        self.retention_combo.addItem("60 days", 60)
        self.retention_combo.addItem("90 days", 90)
        self.retention_combo.addItem("180 days", 180)
        self.retention_combo.addItem("365 days", 365)
        data_layout.addRow(
            self._create_labeled_icon_widget(
                "Keep data for:",
                "How long to keep typing history. 'Keep forever' never deletes data.",
            ),
            self.retention_combo,
        )

        data_actions_layout = QHBoxLayout()
        export_btn = QPushButton("Export to CSV")
        export_btn.clicked.connect(self.export_csv)
        data_actions_layout.addWidget(export_btn)

        clear_btn = QPushButton("Clear All Data")
        clear_btn.clicked.connect(self.clear_data)
        clear_btn.setStyleSheet("QPushButton { background-color: #d32f2f; color: white; }")
        data_actions_layout.addWidget(clear_btn)

        data_layout.addRow(data_actions_layout)
        data_group.setLayout(data_layout)
        layout.addWidget(data_group)

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

        # Speed validation settings
        speed_group = QGroupBox("Speed Validation")
        speed_layout = QFormLayout()

        self.max_realistic_wpm_spin = QSpinBox()
        self.max_realistic_wpm_spin.setRange(101, 500)
        self.max_realistic_wpm_spin.setSuffix(" WPM")
        self.max_realistic_wpm_spin.setValue(300)
        speed_layout.addRow(
            self._create_labeled_icon_widget(
                "Maximum realistic WPM:",
                "Bursts exceeding this WPM are considered unrealistic.\n"
                "They will be ignored and not stored to prevent data corruption.\n"
                "Default: 300 WPM (typical human maximum is ~200 WPM).",
            ),
            self.max_realistic_wpm_spin,
        )

        self.unrealistic_speed_warning_check = QCheckBox("Enable warnings")
        self.unrealistic_speed_warning_check.setChecked(True)
        self.unrealistic_speed_warning_check.setToolTip(
            "Show desktop notification when unrealistic typing speed is detected."
        )
        speed_layout.addRow("", self.unrealistic_speed_warning_check)

        speed_group.setLayout(speed_layout)
        layout.addWidget(speed_group)

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

        # Ignored Words Management Group
        ignored_group = QGroupBox("Ignored Words")
        ignored_layout = QVBoxLayout()

        info_label = QLabel(
            "Words added here will be excluded from word statistics.\n"
            "Privacy: Words are encrypted before storage, so they cannot be retrieved."
        )
        info_label.setWordWrap(True)
        ignored_layout.addWidget(info_label)

        # Input field and button
        input_container = QWidget()
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(0, 0, 0, 0)

        self.ignore_word_input = QLineEdit()
        self.ignore_word_input.setPlaceholderText("Enter a word to ignore...")
        input_layout.addWidget(self.ignore_word_input)

        add_ignore_btn = QPushButton("Add Word")
        add_ignore_btn.clicked.connect(self.add_ignored_word)
        input_layout.addWidget(add_ignore_btn)

        ignored_layout.addWidget(input_container)

        # Status label
        self.ignore_status_label = QLabel()
        self.ignore_status_label.setWordWrap(True)
        self.ignore_status_label.setStyleSheet("color: #666; font-style: italic;")
        ignored_layout.addWidget(self.ignore_status_label)

        ignored_group.setLayout(ignored_layout)
        layout.addWidget(ignored_group)

        # Names Exclusion Group
        names_group = QGroupBox("Names Exclusion")
        names_layout = QVBoxLayout()

        self.exclude_names_check = QCheckBox("Exclude common names from word statistics")
        self.exclude_names_check.setToolTip(
            "Automatically filter out common first names and surnames.\n"
            "Uses embedded list of popular names for enabled languages.\n"
            "Names not in the list can still be added manually to ignored words."
        )
        self.exclude_names_check.stateChanged.connect(self.on_exclude_names_changed)
        names_layout.addWidget(self.exclude_names_check)

        info_label = QLabel(
            "This prevents personal names from appearing in word statistics.\n"
            "The names list is embedded in the application and covers the most\n"
            "common first names and surnames for enabled languages."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; font-size: 11px;")
        names_layout.addWidget(info_label)

        names_group.setLayout(names_layout)
        layout.addWidget(names_group)

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

        # Remote sync checkbox
        sync_group = QGroupBox("Remote Sync")
        sync_layout = QVBoxLayout()

        self.postgres_sync_enabled_check = QCheckBox("Enable PostgreSQL sync")
        self.postgres_sync_enabled_check.setToolTip(
            "Sync typing data with a remote PostgreSQL database for multi-device support.\n\n"
            "Your data is always stored locally in SQLite. PostgreSQL is only used for syncing."
        )
        sync_layout.addWidget(self.postgres_sync_enabled_check)

        sync_group.setLayout(sync_layout)
        layout.addWidget(sync_group)

        # PostgreSQL connection settings
        postgres_group = QGroupBox("PostgreSQL Connection")
        postgres_layout = QFormLayout()

        self.postgres_host_edit = ""
        self.postgres_host_input = QLineEdit()
        self.postgres_host_input.setPlaceholderText("localhost")
        postgres_layout.addRow("Host:", self.postgres_host_input)

        self.postgres_port_spin = QSpinBox()
        self.postgres_port_spin.setRange(1, 65535)
        self.postgres_port_spin.setValue(5432)
        postgres_layout.addRow("Port:", self.postgres_port_spin)

        self.postgres_database_input = QLineEdit()
        self.postgres_database_input.setPlaceholderText("realtypecoach")
        postgres_layout.addRow("Database:", self.postgres_database_input)

        self.postgres_user_input = QLineEdit()
        self.postgres_user_input.setPlaceholderText("realtypecoach")
        postgres_layout.addRow("User:", self.postgres_user_input)

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

        postgres_layout.addRow("Password:", password_container)

        self.sslmode_combo = QComboBox()
        self.sslmode_combo.addItem("Require", "require")
        self.sslmode_combo.addItem("Verify Full", "verify-full")
        self.sslmode_combo.addItem("Prefer", "prefer")
        self.sslmode_combo.addItem("Allow", "allow")
        self.sslmode_combo.addItem("Disable", "disable")
        postgres_layout.addRow("SSL mode:", self.sslmode_combo)

        postgres_group.setLayout(postgres_layout)
        layout.addWidget(postgres_group)

        # Test connection and verify setup buttons
        test_conn_layout = QHBoxLayout()
        test_conn_layout.addStretch()
        self.test_conn_btn = QPushButton("Test Connection")
        self.test_conn_btn.clicked.connect(self.test_postgres_connection)
        test_conn_layout.addWidget(self.test_conn_btn)
        self.verify_setup_btn = QPushButton("Verify Sync Setup")
        self.verify_setup_btn.clicked.connect(self.test_user_and_encryption)
        test_conn_layout.addWidget(self.verify_setup_btn)
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
        user_layout.addRow("User ID:", self.user_id_label)

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

        user_layout.addRow("Username:", username_container)

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

        # Manual Sync Group
        manual_sync_group = QGroupBox("Sync")
        manual_sync_layout = QVBoxLayout()

        self.upload_history_btn = QPushButton("Sync Now")
        self.upload_history_btn.clicked.connect(self.upload_history_to_database)
        manual_sync_layout.addWidget(self.upload_history_btn)

        self.last_sync_label = QLabel("Never synced")
        self.last_sync_label.setStyleSheet("color: #666; font-style: italic;")
        manual_sync_layout.addWidget(self.last_sync_label)

        manual_sync_group.setLayout(manual_sync_layout)
        layout.addWidget(manual_sync_group)

        # Auto-sync settings
        auto_sync_group = QGroupBox("Auto-sync")
        auto_sync_layout = QFormLayout()

        self.auto_sync_enabled_check = QCheckBox("Enable automatic sync")
        auto_sync_layout.addRow("", self.auto_sync_enabled_check)

        self.sync_interval_spin = QSpinBox()
        self.sync_interval_spin.setRange(60, 86400)
        self.sync_interval_spin.setValue(300)
        self.sync_interval_spin.setSuffix(" s")
        auto_sync_layout.addRow("Interval:", self.sync_interval_spin)

        auto_sync_group.setLayout(auto_sync_layout)
        layout.addWidget(auto_sync_group)

        layout.addStretch()
        widget.setLayout(layout)

        # Connect checkbox to enable/disable postgres settings
        self.postgres_sync_enabled_check.stateChanged.connect(self.on_postgres_sync_changed)

        return widget

    def create_llm_tab(self) -> QWidget:
        """Create LLM settings tab."""
        widget = QWidget()
        layout = QVBoxLayout()

        # Status Group
        status_group = QGroupBox("Connection Status")
        status_layout = QVBoxLayout()

        self.llm_status_label = QLabel("Checking connection...")
        self.llm_status_label.setStyleSheet("font-weight: bold;")
        status_layout.addWidget(self.llm_status_label)

        info_label = QLabel(
            "Ollama must be running to use LLM features. Start with: just start-ollama"
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: gray; font-size: 11px;")
        status_layout.addWidget(info_label)

        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        # Model Selection Group
        model_group = QGroupBox("Model Selection")
        model_layout = QFormLayout()

        self.llm_model_combo = QComboBox()
        self.llm_model_combo.setMinimumWidth(300)
        model_layout.addRow("Model:", self.llm_model_combo)

        refresh_models_btn = QPushButton("Refresh Models")
        refresh_models_btn.clicked.connect(self._refresh_llm_models)
        model_layout.addRow("", refresh_models_btn)

        # Add test button row with button and result label
        test_layout = QHBoxLayout()
        test_llm_btn = QPushButton("🧪 Test Connection")
        test_llm_btn.clicked.connect(self._test_llm_connection)
        test_layout.addWidget(test_llm_btn)

        self.llm_test_result = QLabel()
        self.llm_test_result.setWordWrap(True)
        self.llm_test_result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        test_layout.addWidget(self.llm_test_result, stretch=1)

        model_layout.addRow("", test_layout)

        model_group.setLayout(model_layout)
        layout.addWidget(model_group)

        # Text Generation Settings Group
        text_group = QGroupBox("Text Generation")
        text_layout = QFormLayout()

        self.llm_word_count_spin = QSpinBox()
        self.llm_word_count_spin.setMinimum(10)
        self.llm_word_count_spin.setMaximum(500)
        self.llm_word_count_spin.setValue(50)
        self.llm_word_count_spin.setSingleStep(10)
        text_layout.addRow("Target Word Count:", self.llm_word_count_spin)

        text_group.setLayout(text_layout)
        layout.addWidget(text_group)

        # Prompt Management Group
        prompt_group = QGroupBox("Prompt Templates")
        prompt_layout = QVBoxLayout()

        # Prompt selector
        selector_layout = QHBoxLayout()
        selector_layout.addWidget(QLabel("Active Prompt:"))

        self.llm_prompt_combo = QComboBox()
        self.llm_prompt_combo.setMinimumWidth(250)
        self.llm_prompt_combo.currentIndexChanged.connect(self._on_llm_prompt_changed)
        selector_layout.addWidget(self.llm_prompt_combo)

        prompt_layout.addLayout(selector_layout)

        # Prompt editor
        editor_layout = QVBoxLayout()
        editor_layout.addWidget(QLabel("Prompt Template:"))

        self.llm_prompt_editor = QTextEdit()
        self.llm_prompt_editor.setPlaceholderText(
            "Use {word_count} and {hardest_words} placeholders..."
        )
        self.llm_prompt_editor.setMinimumHeight(150)
        editor_layout.addWidget(self.llm_prompt_editor)

        # Buttons
        buttons_layout = QHBoxLayout()

        save_btn = QPushButton("Save")
        save_btn.setToolTip("Update current prompt")
        save_btn.clicked.connect(self._save_llm_prompt)
        buttons_layout.addWidget(save_btn)

        save_as_btn = QPushButton("Save As...")
        save_as_btn.setToolTip("Create new prompt from current content")
        save_as_btn.clicked.connect(self._save_llm_prompt_as)
        buttons_layout.addWidget(save_as_btn)

        delete_btn = QPushButton("Delete")
        delete_btn.setToolTip("Delete prompt")
        delete_btn.setStyleSheet("QPushButton { background-color: #d32f2f; color: white; }")
        delete_btn.clicked.connect(self._delete_llm_prompt)
        buttons_layout.addWidget(delete_btn)

        reset_btn = QPushButton("Reset All")
        reset_btn.setToolTip("Reset all prompts to defaults")
        reset_btn.setStyleSheet("QPushButton { background-color: #f57c00; color: white; }")
        reset_btn.clicked.connect(self._reset_llm_prompts)
        buttons_layout.addWidget(reset_btn)

        editor_layout.addLayout(buttons_layout)
        prompt_layout.insertLayout(1, editor_layout)

        # Placeholders info
        placeholders_label = QLabel("Available placeholders: {word_count}, {hardest_words}")
        placeholders_label.setStyleSheet("color: gray; font-size: 10px; padding: 5px;")
        placeholders_label.setWordWrap(True)
        prompt_layout.addWidget(placeholders_label)

        prompt_group.setLayout(prompt_layout)
        layout.addWidget(prompt_group)

        # Add stretch to push everything to top
        layout.addStretch()

        widget.setLayout(layout)
        return widget

    def set_ollama_available(self, available: bool) -> None:
        """Set Ollama availability and update LLM tab.

        Args:
            available: True if Ollama is available
        """
        self.ollama_available = available

        # Find LLM tab and enable/disable
        tabs = self.findChild(QTabWidget)
        if tabs:
            llm_tab_index = tabs.count() - 1  # LLM is last tab
            tabs.setTabEnabled(llm_tab_index, available)

            # Update status label
            if hasattr(self, "llm_status_label"):
                if available:
                    model = self.current_settings.get("llm_model", "Unknown")
                    self.llm_status_label.setText(f"✓ Connected: {model}")
                    self.llm_status_label.setStyleSheet("color: green;")
                else:
                    self.llm_status_label.setText("✗ Not connected")
                    self.llm_status_label.setStyleSheet("color: red;")

    def on_postgres_sync_changed(self) -> None:
        """Handle PostgreSQL sync checkbox change."""
        is_enabled = self.postgres_sync_enabled_check.isChecked()

        # Enable/disable postgres settings based on checkbox state
        postgres_widgets = [
            self.postgres_host_input,
            self.postgres_port_spin,
            self.postgres_database_input,
            self.postgres_user_input,
            self.postgres_password_input,
            self.sslmode_combo,
            self.test_conn_btn,
            self.verify_setup_btn,
        ]

        for widget in postgres_widgets:
            widget.setEnabled(is_enabled)

        # Enable/disable user identity and sync widgets
        user_sync_widgets = [
            self.user_id_label,
            self.username_edit,
            self.export_key_btn,
            self.import_key_btn,
            self.upload_history_btn,
        ]

        for widget in user_sync_widgets:
            widget.setEnabled(is_enabled)

        # Enable/disable auto-sync widgets (only when sync is enabled)
        auto_sync_widgets = [
            self.auto_sync_enabled_check,
            self.sync_interval_spin,
        ]

        for widget in auto_sync_widgets:
            widget.setEnabled(is_enabled)

    def on_exclude_names_changed(self) -> None:
        """Handle exclude names checkbox change."""
        is_checked = self.exclude_names_check.isChecked()

        # Only handle when enabling (False → True)
        if not is_checked:
            return

        # Check if this was previously disabled (from current settings)
        was_disabled = not self.current_settings.get("exclude_names_enabled", False)

        if was_disabled:
            # Block signals to prevent recursive calls
            self.exclude_names_check.blockSignals(True)

            from PySide6.QtWidgets import QMessageBox

            reply = QMessageBox.question(
                self,
                "Delete All Name Statistics?",
                "This will delete all existing name statistics (e.g., 'Melanie', 'John', 'Smith')\n"
                "from the database. This action cannot be undone.\n\n"
                "Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if reply == QMessageBox.StandardButton.Yes:
                # Delete names from database
                if self.storage:
                    try:
                        deleted_count = self.storage.delete_all_names_from_database()
                        # Update the running dictionary's flag so NEW names are also filtered
                        self.storage.update_exclude_names_setting(True)
                        log.info("Updated dictionary exclude_names setting to True")
                        QMessageBox.information(
                            self,
                            "Names Deleted",
                            f"Successfully deleted {deleted_count} name statistics from the database.",
                        )
                    except Exception as e:
                        QMessageBox.critical(
                            self,
                            "Deletion Failed",
                            f"Failed to delete name statistics:\n{e}",
                        )
                        # Revert checkbox on error
                        self.exclude_names_check.setChecked(False)
            else:
                # User cancelled, revert checkbox
                self.exclude_names_check.setChecked(False)

            # Unblock signals
            self.exclude_names_check.blockSignals(False)

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

    def test_user_and_encryption(self) -> None:
        """Verify user presence and encryption key functionality."""
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
        from core.user_manager import UserManager
        from utils.config import Config
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

        # Get user_id
        config = Config(db_path)
        user_manager = UserManager(db_path, config)
        try:
            current_user = user_manager.get_or_create_current_user()
            user_id = current_user.user_id
        except Exception as e:
            self.conn_status_label.setText(f"Failed to get user: {str(e)}")
            self.conn_status_label.setStyleSheet("color: red; font-style: italic;")
            return

        # Get encryption key
        try:
            encryption_key = user_manager.get_encryption_key()
        except Exception as e:
            self.conn_status_label.setText(f"Failed to get encryption key: {str(e)}")
            self.conn_status_label.setStyleSheet("color: red; font-style: italic;")
            return

        self.conn_status_label.setText("Verifying sync setup...")
        self.conn_status_label.setStyleSheet("color: #666; font-style: italic;")
        QApplication.processEvents()

        status_lines = []
        all_passed = True

        try:
            # Test PostgreSQL connection
            conn = psycopg2.connect(
                host=host,
                port=port,
                database=database,
                user=user,
                password=password,
                sslmode=sslmode,
                connect_timeout=10,
            )
            from core.data_encryption import DataEncryption
            from core.postgres_adapter import PostgreSQLAdapter

            # Create a temporary adapter to run the checks
            adapter = PostgreSQLAdapter(
                host=host,
                port=port,
                database=database,
                user=user,
                password=password,
                sslmode=sslmode,
                user_id=user_id,
            )
            adapter.initialize()

            # Check if user exists
            user_exists = adapter.check_user_exists(user_id)
            if user_exists:
                status_lines.append("✓ User found in remote database")
            else:
                # Create user in remote database
                try:
                    adapter.register_user(user_id, current_user.username)
                    status_lines.append("✓ User created in remote database")
                except Exception as e:
                    status_lines.append(f"✗ Failed to create user in remote database: {str(e)}")
                    all_passed = False

            # Test encryption/decryption
            test_record = adapter.get_test_record_for_decryption(user_id)
            if test_record is None:
                status_lines.append("⚠ No encrypted data found to test encryption key")
            else:
                try:
                    encryption = DataEncryption(encryption_key)
                    decrypted = encryption.decrypt_burst(test_record["encrypted_data"])
                    status_lines.append("✓ Encryption key verified (decrypted test record)")
                except Exception as e:
                    status_lines.append(f"✗ Encryption key test failed: {str(e)}")
                    all_passed = False

            conn.close()

        except Exception as e:
            status_lines.append(f"✗ Verification failed: {str(e)}")
            all_passed = False

        self.conn_status_label.setText("\n".join(status_lines))
        self.conn_status_label.setStyleSheet(
            "color: green; font-style: italic;"
            if all_passed
            else "color: orange; font-style: italic;"
        )

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

    def add_ignored_word(self) -> None:
        """Add a word to the ignored list."""
        from PySide6.QtWidgets import QMessageBox

        word = self.ignore_word_input.text().strip()

        if not word:
            QMessageBox.warning(self, "Empty Word", "Please enter a word to ignore.")
            return

        # Validate: only letters allowed
        if not word.isalpha():
            QMessageBox.warning(
                self, "Invalid Word", "Only letters (a-z) are allowed in ignored words."
            )
            return

        if len(word) < 3:
            QMessageBox.warning(self, "Word Too Short", "Words must be at least 3 letters long.")
            return

        # Check if storage is available
        if self.storage is None:
            QMessageBox.warning(
                self, "Storage Not Available", "Please restart the application and try again."
            )
            return

        # Add the word
        success, deleted_count = self.storage.add_ignored_word(word)

        if success:
            self.ignore_word_input.clear()
            self.ignore_status_label.setText(
                f"Added '{word}' to ignored list. Deleted {deleted_count} statistics."
            )
            self.ignore_status_label.setStyleSheet("color: green; font-style: italic;")
        else:
            self.ignore_status_label.setText(f"Word '{word}' is already in the ignored list.")
            self.ignore_status_label.setStyleSheet("color: orange; font-style: italic;")

    # ========== LLM Tab Handlers ==========

    def _refresh_llm_models(self) -> None:
        """Refresh available Ollama models."""
        from PySide6.QtWidgets import QMessageBox

        if not self.ollama_available:
            QMessageBox.warning(self, "Ollama Not Available", "Ollama server is not running.")
            return

        try:
            # Get models from Ollama (cached from main application)
            models = self._available_models

            # Update combo box
            self.llm_model_combo.clear()
            for model in models:
                self.llm_model_combo.addItem(model, model)

            # Select current model, with fallback to available model
            current_model = self.current_settings.get("llm_model", "gemma2:2b")
            index = self.llm_model_combo.findData(current_model)
            if index < 0 and models:
                # Current model not available, use first available model
                index = 0
                log.warning(
                    f"Configured model '{current_model}' not available, using '{models[0]}' instead"
                )
            if index >= 0:
                self.llm_model_combo.setCurrentIndex(index)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to fetch models: {e}")

    def _on_llm_model_changed(self) -> None:
        """Handle model selection change."""
        pass  # Model will be saved in get_settings()

    def _test_llm_connection(self) -> None:
        """Test Ollama connection by generating a haiku."""
        from PySide6.QtCore import QThread, Signal

        class TestWorker(QThread):
            """Worker thread for testing Ollama connection."""

            finished = Signal(str, bool)  # (result_text, success)

            def __init__(self, model: str):
                super().__init__()
                self.model = model

            def run(self) -> None:
                """Test connection by generating a haiku."""
                try:
                    import ollama

                    client = ollama.Client(host="localhost:11434")
                    response = client.generate(
                        model=self.model,
                        prompt="Write a short haiku about programming.",
                        stream=False,
                        options={"temperature": 0.7},
                    )

                    result = response.get("response", "").strip()
                    if result:
                        self.finished.emit(result, True)
                    else:
                        self.finished.emit("✗ Empty response from Ollama", False)

                except Exception as e:
                    error_msg = f"✗ Error: {str(e)}"
                    self.finished.emit(error_msg, False)

        # Update UI to show testing
        self.llm_test_result.setText("⏳ Testing...")
        self.llm_test_result.setStyleSheet("QLabel { color: orange; }")
        current_model = self.llm_model_combo.currentData()

        if not current_model:
            self.llm_test_result.setText("✗ No model selected")
            self.llm_test_result.setStyleSheet("QLabel { color: red; }")
            return

        # Start worker thread
        self._test_worker = TestWorker(current_model)
        self._test_worker.finished.connect(self._on_llm_test_complete)
        self._test_worker.start()

    def _on_llm_test_complete(self, result: str, success: bool) -> None:
        """Handle LLM test completion.

        Args:
            result: Generated text or error message
            success: True if test succeeded
        """
        if success:
            # Display the haiku with success styling
            self.llm_test_result.setText(f"✓ Success!\n\n{result}")
            self.llm_test_result.setStyleSheet("QLabel { color: green; }")
        else:
            # Display error with error styling
            self.llm_test_result.setText(result)
            self.llm_test_result.setStyleSheet("QLabel { color: red; }")

    def _load_llm_prompts(self) -> None:
        """Load prompts from database into combo box."""
        if not self.storage:
            return

        try:
            prompts = self.storage.get_all_prompts()

            self.llm_prompt_combo.clear()
            for prompt in prompts:
                display_name = f"{'★ ' if prompt['is_default'] else ''}{prompt['name']}"
                self.llm_prompt_combo.addItem(display_name, prompt["id"])

            # Select active prompt
            active_id = self.current_settings.get("llm_active_prompt_id", -1)
            if active_id >= 0:
                index = self.llm_prompt_combo.findData(active_id)
                if index >= 0:
                    self.llm_prompt_combo.setCurrentIndex(index)
            elif prompts:
                self.llm_prompt_combo.setCurrentIndex(0)

            # Load prompt content
            self._load_prompt_content()

        except Exception as e:
            log.error(f"Failed to load prompts: {e}")

    def _on_llm_prompt_changed(self) -> None:
        """Handle prompt selection change."""
        self._load_prompt_content()

    def _load_prompt_content(self) -> None:
        """Load selected prompt content into editor."""
        prompt_id = self.llm_prompt_combo.currentData()
        if prompt_id is None:
            return

        try:
            prompt = self.storage.get_prompt(prompt_id)
            if prompt:
                self.llm_prompt_editor.setPlainText(prompt["content"])
        except Exception as e:
            log.error(f"Failed to load prompt: {e}")

    def _save_llm_prompt(self) -> None:
        """Save prompt content to current prompt (no name dialog for existing prompts)."""
        from PySide6.QtWidgets import QMessageBox

        if not self.storage:
            return

        prompt_id = self.llm_prompt_combo.currentData()
        content = self.llm_prompt_editor.toPlainText()

        # No prompt selected - ask for name to create new one
        if prompt_id is None:
            name, ok = QInputDialog.getText(
                self, "New Prompt", "Enter a name for this prompt:", text="My Custom Prompt"
            )
            if not ok or not name:
                return

            try:
                new_prompt_id = self.storage.create_prompt(name, content)
                self._load_llm_prompts()
                index = self.llm_prompt_combo.findData(new_prompt_id)
                if index >= 0:
                    self.llm_prompt_combo.setCurrentIndex(index)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save prompt: {e}")
            return

        # Editing existing prompt - check if it's a default prompt
        try:
            prompt = self.storage.get_prompt(prompt_id)
            if not prompt:
                QMessageBox.warning(self, "Error", "Could not find the selected prompt.")
                return

            # Warn if trying to save over a default prompt
            if prompt.get("is_default"):
                reply = QMessageBox.question(
                    self,
                    "Cannot Modify Default Prompt",
                    "Default prompts cannot be modified directly.\n\n"
                    "Use 'Save As' to create a custom copy.",
                    QMessageBox.StandardButton.Ok,
                )
                return

            # Save content with existing name (no dialog!)
            self.storage.update_prompt(prompt_id, prompt["name"], content)

            # Reload prompts to reflect changes (e.g., updated_at timestamp)
            self._load_llm_prompts()
            index = self.llm_prompt_combo.findData(prompt_id)
            if index >= 0:
                self.llm_prompt_combo.setCurrentIndex(index)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save prompt: {e}")

    def _save_llm_prompt_as(self) -> None:
        """Save current content as a new prompt (duplicate)."""
        from PySide6.QtWidgets import QMessageBox

        if not self.storage:
            return

        content = self.llm_prompt_editor.toPlainText()
        current_prompt_id = self.llm_prompt_combo.currentData()

        # Get current prompt name for default suggestion
        default_name = "My Custom Prompt"
        if current_prompt_id:
            try:
                current = self.storage.get_prompt(current_prompt_id)
                if current:
                    default_name = f"Copy of {current['name']}"
            except Exception:
                pass

        # Ask for new name
        name, ok = QInputDialog.getText(
            self, "Save As", "Enter a name for the new prompt:", text=default_name
        )

        if not ok or not name:
            return

        try:
            # Create new prompt with current content
            new_prompt_id = self.storage.create_prompt(name, content)

            # Reload and select the new prompt
            self._load_llm_prompts()
            index = self.llm_prompt_combo.findData(new_prompt_id)
            if index >= 0:
                self.llm_prompt_combo.setCurrentIndex(index)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save prompt: {e}")

    def _delete_llm_prompt(self) -> None:
        """Delete selected prompt."""
        from PySide6.QtWidgets import QMessageBox

        if not self.storage:
            return

        prompt_id = self.llm_prompt_combo.currentData()
        if prompt_id is None:
            QMessageBox.warning(self, "No Selection", "No prompt selected.")
            return

        # Check if default prompt
        prompt = self.storage.get_prompt(prompt_id)
        if prompt and prompt.get("is_default"):
            QMessageBox.warning(self, "Cannot Delete", "Default prompts cannot be deleted.")
            return

        try:
            self.storage.delete_prompt(prompt_id)
            self._load_llm_prompts()
            QMessageBox.information(self, "Success", "Prompt deleted.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to delete: {e}")

    def _reset_llm_prompts(self) -> None:
        """Reset all prompts to defaults."""
        from PySide6.QtWidgets import QMessageBox

        reply = QMessageBox.warning(
            self,
            "Confirm Reset",
            "This will delete all custom prompts and reset to the 3 default prompts.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.storage.reset_default_prompts()
                self._load_llm_prompts()
                QMessageBox.information(self, "Success", "Prompts reset to defaults.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to reset: {e}")

    def load_current_settings(self) -> None:
        """Load current settings into UI."""
        self.burst_timeout_spin.setValue(
            int(self.current_settings.get("burst_timeout_ms", 1000) or 1000)
        )
        self.word_boundary_timeout_spin.setValue(
            int(self.current_settings.get("word_boundary_timeout_ms", 1000) or 1000)
        )

        # Load duration calculation method
        duration_method = self.current_settings.get("burst_duration_calculation", "total_time")
        index = self.duration_method_combo.findData(duration_method)
        if index >= 0:
            self.duration_method_combo.setCurrentIndex(index)

        self.active_threshold_spin.setValue(
            int(self.current_settings.get("active_time_threshold_ms", 500) or 500)
        )

        self.high_score_duration_spin.setValue(
            int(self.current_settings.get("high_score_min_duration_ms", 5000) or 5000)
        )
        self.min_key_count_spin.setValue(
            int(self.current_settings.get("min_burst_key_count", 10) or 10)
        )
        self.min_burst_duration_spin.setValue(
            int(self.current_settings.get("min_burst_duration_ms", 5000) or 5000)
        )
        self.keyboard_layout_combo.setCurrentText(
            self.current_settings.get("keyboard_layout", "Auto-detect").capitalize()
        )
        self.stats_update_interval_spin.setValue(
            int(self.current_settings.get("stats_update_interval_sec", 2) or 2)
        )
        self.notification_min_burst_spin.setValue(
            int(self.current_settings.get("notification_min_burst_ms", 10000) or 10000) // 1000
        )
        self.notification_threshold_days_spin.setValue(
            int(self.current_settings.get("notification_threshold_days", 30) or 30)
        )
        self.notification_threshold_update_spin.setValue(
            int(self.current_settings.get("notification_threshold_update_sec", 300) or 300)
        )
        self.notification_hour_spin.setValue(
            int(self.current_settings.get("notification_time_hour", 18) or 18)
        )
        self.daily_summary_enabled_check.setChecked(
            self.current_settings.get("daily_summary_enabled", True)
        )
        self.worst_letter_notification_check.setChecked(
            self.current_settings.get("worst_letter_notifications_enabled", False)
        )
        self.worst_letter_debounce_spin.setValue(
            int(self.current_settings.get("worst_letter_notification_debounce_min", 5) or 5)
        )
        # Load speed validation settings
        self.max_realistic_wpm_spin.setValue(
            int(self.current_settings.get("max_realistic_wpm", 300) or 300)
        )
        self.unrealistic_speed_warning_check.setChecked(
            self.current_settings.get("unrealistic_speed_warning_enabled", True)
        )
        retention_days = self.current_settings.get("data_retention_days", -1)
        index = self.retention_combo.findData(retention_days)
        if index >= 0:
            self.retention_combo.setCurrentIndex(index)

        # Load dictionary mode
        dict_mode = self.current_settings.get("dictionary_mode", "validate")
        self.validate_mode_radio.setChecked(dict_mode == "validate")

        # Load exclude names setting
        self.exclude_names_check.setChecked(
            self.current_settings.get("exclude_names_enabled", False)
        )

        # Load database settings
        postgres_sync_enabled = self.current_settings.get("postgres_sync_enabled", False)
        log.info(
            f"load_current_settings: postgres_sync_enabled = {postgres_sync_enabled!r} (type: {type(postgres_sync_enabled).__name__})"
        )
        self.postgres_sync_enabled_check.setChecked(postgres_sync_enabled)

        self.postgres_host_input.setText(self.current_settings.get("postgres_host", ""))
        self.postgres_port_spin.setValue(
            int(self.current_settings.get("postgres_port", 5432) or 5432)
        )
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
        sync_interval = self.current_settings.get("auto_sync_interval_sec", 300)
        self.sync_interval_spin.setValue(int(sync_interval) if sync_interval else 300)

        # Trigger postgres sync changed to enable/disable postgres settings
        self.on_postgres_sync_changed()

        # LLM settings
        self.llm_model_combo.setCurrentIndex(
            self.llm_model_combo.findData(self.current_settings.get("llm_model", "gemma2:2b"))
        )

        word_count = self.current_settings.get("llm_word_count", 50)
        self.llm_word_count_spin.setValue(int(word_count) if word_count else 50)

        active_prompt_id = self.current_settings.get("llm_active_prompt_id", -1)
        if active_prompt_id >= 0:
            self.llm_prompt_combo.setCurrentIndex(self.llm_prompt_combo.findData(active_prompt_id))

        # Load prompts from database
        self._load_llm_prompts()

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

        # Capture checkbox states for logging
        postgres_sync_check_state = self.postgres_sync_enabled_check.isChecked()
        auto_sync_check_state = self.auto_sync_enabled_check.isChecked()
        log.info(
            f"get_settings: postgres_sync_enabled checkbox = {postgres_sync_check_state!r}, "
            f"auto_sync_enabled checkbox = {auto_sync_check_state!r}"
        )

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
            "max_realistic_wpm": str(self.max_realistic_wpm_spin.value()),
            "unrealistic_speed_warning_enabled": str(
                self.unrealistic_speed_warning_check.isChecked()
            ),
            "data_retention_days": str(self.retention_combo.currentData()),
            "dictionary_mode": "validate" if self.validate_mode_radio.isChecked() else "accept_all",
            "enabled_languages": enabled_langs_str,
            "enabled_dictionaries": enabled_dicts_str,
            "exclude_names_enabled": str(self.exclude_names_check.isChecked()),
            # Database settings
            "postgres_sync_enabled": str(postgres_sync_check_state),
            "postgres_host": self.postgres_host_input.text(),
            "postgres_port": str(self.postgres_port_spin.value()),
            "postgres_database": self.postgres_database_input.text() or "realtypecoach",
            "postgres_user": self.postgres_user_input.text(),
            "postgres_sslmode": self.sslmode_combo.currentData(),
            # Auto-sync settings
            "auto_sync_enabled": str(auto_sync_check_state),
            "auto_sync_interval_sec": str(self.sync_interval_spin.value()),
            # LLM settings
            "llm_model": self.llm_model_combo.currentData() or "gemma2:2b",
            "llm_active_prompt_id": self.llm_prompt_combo.currentData() or -1,
            "llm_word_count": str(self.llm_word_count_spin.value()),
        }

    def accept(self) -> None:
        """Validate and accept the dialog."""
        # Check if postgres sync is enabled
        if self.postgres_sync_enabled_check.isChecked():
            host = self.postgres_host_input.text().strip()
            user = self.postgres_user_input.text().strip()

            if not host:
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.warning(
                    self,
                    "Incomplete PostgreSQL Settings",
                    "PostgreSQL host is required when sync is enabled.\n\n"
                    "Please fill in the host field or disable PostgreSQL sync.",
                )
                self.postgres_host_input.setFocus()
                return

            if not user:
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.warning(
                    self,
                    "Incomplete PostgreSQL Settings",
                    "PostgreSQL user is required when sync is enabled.\n\n"
                    "Please fill in the user field or disable PostgreSQL sync.",
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
        from PySide6.QtWidgets import QMessageBox

        from core.user_manager import UserManager

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
        from PySide6.QtWidgets import QMessageBox, QTextEdit

        from core.user_manager import UserManager

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
        from PySide6.QtWidgets import QTextEdit

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
        import_btn.clicked.connect(
            lambda: self._do_import_key(key_input.toPlainText(), dialog, db_path, config)
        )

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
        QTimer.singleShot(
            1000, lambda: dialog.findChild(QTextEdit, None).setPlainText(original_text)
        )

    def _do_import_key(self, key_data: str, dialog: QDialog, db_path: Path, config) -> None:
        """Actually import the key after validation."""
        from PySide6.QtWidgets import QMessageBox

        from core.user_manager import UserManager

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
        from PySide6.QtWidgets import QMessageBox

        # Check if we have access to storage
        if self.storage is None:
            QMessageBox.warning(
                self,
                "Storage Not Available",
                "Storage instance not available. Please restart the application and try again.",
            )
            return

        # Check if PostgreSQL is configured
        if not self.postgres_sync_enabled_check.isChecked():
            QMessageBox.warning(self, "Not Configured", "Please enable PostgreSQL sync first.")
            return

        host = self.postgres_host_input.text().strip()
        postgres_user = self.postgres_user_input.text().strip()

        if not all([host, postgres_user]):
            QMessageBox.warning(
                self, "Not Configured", "Please configure PostgreSQL connection first."
            )
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
            # Build temporary config overrides from current UI state
            postgres_overrides = {
                "postgres_sync_enabled": self.postgres_sync_enabled_check.isChecked(),
                "postgres_host": host,
                "postgres_port": self.postgres_port_spin.value(),
                "postgres_database": self.postgres_database_input.text().strip() or "realtypecoach",
                "postgres_user": postgres_user,
                "postgres_sslmode": self.sslmode_combo.currentData(),
            }

            log.debug(f"Using temporary config overrides for sync: {postgres_overrides}")

            # Apply temporary config override for this sync operation
            with self.storage.config.temporary_override(postgres_overrides):
                result = self.sync_handler.sync_now()

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
                    f"Merged: {result['merged']} records\n"
                    f"Duration: {result['duration_ms'] / 1000:.2f} s",
                )
            else:
                self.last_sync_label.setText("✗ Sync failed - check logs")
                self.last_sync_label.setStyleSheet("color: red; font-style: italic;")
                QMessageBox.critical(
                    self, "Sync Failed", f"Sync failed:\n{result.get('error', 'Unknown error')}"
                )

        except Exception as e:
            self.last_sync_label.setText("✗ Sync failed - check logs")
            self.last_sync_label.setStyleSheet("color: red; font-style: italic;")
            QMessageBox.critical(self, "Sync Failed", f"Error during sync:\n{e}")
        finally:
            # Always restore button state
            self.upload_history_btn.setEnabled(True)
            self.upload_history_btn.setText("Sync Now")

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

    def _on_sync_completed(self, result: dict) -> None:
        """Handle sync completion from sync handler.

        Args:
            result: Sync result dictionary
        """
        self._update_last_sync_label()
