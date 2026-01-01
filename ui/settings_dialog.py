"""Settings dialog for RealTypeCoach."""

import logging
from typing import Any

from PySide6.QtCore import Qt
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
    QLabel,
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

    def __init__(self, current_settings: dict, parent=None):
        """Initialize settings dialog.

        Args:
            current_settings: Dictionary of current settings
            parent: Parent widget
        """
        super().__init__(parent)
        self.current_settings = current_settings
        self.settings: dict = {}
        # Set window flags for Wayland compatibility
        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        self.init_ui()
        self.load_current_settings()

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
    def _create_labeled_icon_widget(
        label_text: str, tooltip_text: str, parent=None
    ) -> QWidget:
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
        tabs.setTabIcon(
            1, self._create_palette_aware_icon("preferences-desktop-notification")
        )

        data_tab = self.create_data_tab()
        tabs.addTab(data_tab, "Data")
        tabs.setTabIcon(2, self._create_palette_aware_icon("database"))

        language_tab = self.create_language_tab()
        tabs.addTab(language_tab, "Language")
        tabs.setTabIcon(3, self._create_palette_aware_icon("accessories-dictionary"))

        dialog_buttons = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        dialog_buttons.addWidget(ok_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        dialog_buttons.addWidget(cancel_btn)

        layout.addLayout(dialog_buttons)
        self.setLayout(layout)

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

        self.worst_letter_notification_check = QCheckBox(
            "Notify on worst letter change"
        )
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
            "Only store words found in selected dictionaries.\n"
            "Best for accurate word statistics."
        )
        self.validate_mode_radio.setChecked(True)

        mode_layout.addWidget(self.validate_mode_radio)
        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)

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
            enabled_dicts_setting = self.current_settings.get(
                "enabled_dictionaries", ""
            )
            log.info(
                f"rescan: self.current_settings.get('enabled_dictionaries', '') returned: {enabled_dicts_setting!r}"
            )
            if current_ui_selections:
                selected_set = current_ui_selections
                log.info(f"rescan: using current UI selections: {selected_set}")
            elif enabled_dicts_setting and enabled_dicts_setting.strip():
                selected_set = set(
                    p.strip() for p in enabled_dicts_setting.split(",") if p.strip()
                )
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
                        log.debug(
                            f"Not checking {dict_info.path} (not in selected_set)"
                        )
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
                        log.info(
                            f"Checking {dict_info.path} (default American English)"
                        )

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
        self.burst_timeout_spin.setValue(
            self.current_settings.get("burst_timeout_ms", 1000)
        )
        self.word_boundary_timeout_spin.setValue(
            self.current_settings.get("word_boundary_timeout_ms", 1000)
        )

        # Load duration calculation method
        duration_method = self.current_settings.get(
            "burst_duration_calculation", "total_time"
        )
        index = self.duration_method_combo.findData(duration_method)
        if index >= 0:
            self.duration_method_combo.setCurrentIndex(index)

        self.active_threshold_spin.setValue(
            self.current_settings.get("active_time_threshold_ms", 500)
        )

        self.high_score_duration_spin.setValue(
            self.current_settings.get("high_score_min_duration_ms", 5000)
        )
        self.min_key_count_spin.setValue(
            self.current_settings.get("min_burst_key_count", 10)
        )
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
        enabled_langs_str = (
            ",".join(sorted(enabled_lang_codes)) if enabled_lang_codes else "en,de"
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
            "notification_min_burst_ms": str(
                self.notification_min_burst_spin.value() * 1000
            ),
            "notification_threshold_days": str(
                self.notification_threshold_days_spin.value()
            ),
            "notification_threshold_update_sec": str(
                self.notification_threshold_update_spin.value()
            ),
            "notification_time_hour": str(self.notification_hour_spin.value()),
            "daily_summary_enabled": str(self.daily_summary_enabled_check.isChecked()),
            "worst_letter_notifications_enabled": str(
                self.worst_letter_notification_check.isChecked()
            ),
            "worst_letter_notification_debounce_min": str(
                self.worst_letter_debounce_spin.value()
            ),
            "data_retention_days": str(self.retention_combo.currentData()),
            "dictionary_mode": "validate"
            if self.validate_mode_radio.isChecked()
            else "accept_all",
            "enabled_languages": enabled_langs_str,
            "enabled_dictionaries": enabled_dicts_str,
        }

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
            "Are you sure you want to delete all typing data?\n\n"
            "This action cannot be undone!",
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
                painter.fillRect(
                    pixmap.rect(), button.palette().color(QPalette.ButtonText)
                )
                painter.end()
                button.setIcon(QIcon(pixmap))

        reply = msg_box.exec()

        if reply == QMessageBox.Yes:
            self.settings = self.get_settings()
            self.settings["__clear_database__"] = True
            self.accept()
