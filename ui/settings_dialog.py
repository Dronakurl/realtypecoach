"""Settings dialog for RealTypeCoach."""

import logging
from typing import Any

from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QDoubleSpinBox,
    QCheckBox,
    QPushButton,
    QFileDialog,
    QGroupBox,
    QFormLayout,
    QComboBox,
    QTabWidget,
    QWidget,
    QListWidget,
    QApplication,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QPixmap, QImage, QColor, QPalette

log = logging.getLogger("realtypecoach.settings_dialog")


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
        icon = QIcon.fromTheme(theme_name)
        if icon.isNull():
            return icon

        # Get the application's palette text color
        palette = QApplication.palette()
        text_color = palette.color(QPalette.Text)

        # Colorize the icon for multiple sizes
        colorized_icon = QIcon()
        sizes = [16, 22, 24, 32]

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

        return colorized_icon if not colorized_icon.isNull() else icon

    def init_ui(self) -> None:
        """Initialize user interface."""
        self.setWindowTitle("RealTypeCoach Settings")
        self.setMinimumWidth(500)

        layout = QVBoxLayout()

        tabs = QTabWidget()
        layout.addWidget(tabs)

        general_tab = self.create_general_tab()
        tabs.addTab(
            general_tab,
            self._create_palette_aware_icon("preferences-system"),
            "General",
        )

        notification_tab = self.create_notification_tab()
        tabs.addTab(
            notification_tab,
            self._create_palette_aware_icon("preferences-desktop-notification"),
            "Notifications",
        )

        data_tab = self.create_data_tab()
        tabs.addTab(data_tab, self._create_palette_aware_icon("database"), "Data")

        language_tab = self.create_language_tab()
        tabs.addTab(
            language_tab,
            self._create_palette_aware_icon("accessories-dictionary"),
            "Language",
        )

        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        export_btn = QPushButton("Export to CSV")
        export_btn.clicked.connect(self.export_csv)
        buttons_layout.addWidget(export_btn)

        clear_btn = QPushButton("Clear All Data")
        clear_btn.setStyleSheet("background-color: #ff6b6b; color: white;")
        clear_btn.clicked.connect(self.clear_data)
        buttons_layout.addWidget(clear_btn)

        layout.addLayout(buttons_layout)

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
        self.burst_timeout_spin.setToolTip(
            "Maximum pause between keystrokes before burst ends.\n"
            "Shorter timeout = bursts split more frequently"
        )
        burst_layout.addRow("Burst timeout:", self.burst_timeout_spin)

        self.word_boundary_timeout_spin = QSpinBox()
        self.word_boundary_timeout_spin.setRange(100, 10000)
        self.word_boundary_timeout_spin.setSuffix(" ms")
        self.word_boundary_timeout_spin.setValue(1000)
        self.word_boundary_timeout_spin.setToolTip(
            "Maximum pause between letters before word is split.\n"
            "Example: 'br' [pause] 'own' becomes two fragments instead of 'brown'\n"
            "Shorter timeout = more conservative word detection"
        )
        burst_layout.addRow("Word boundary timeout:", self.word_boundary_timeout_spin)

        self.duration_method_combo = QComboBox()
        self.duration_method_combo.addItem("Total Time (includes pauses)", "total_time")
        self.duration_method_combo.addItem("Active Time (typing only)", "active_time")
        self.duration_method_combo.setToolTip(
            "How burst duration is calculated:\n"
            "• Total Time: Includes all time from first to last keystroke\n"
            "• Active Time: Only counts time actually spent typing"
        )
        burst_layout.addRow("Duration calculation:", self.duration_method_combo)

        self.active_threshold_spin = QSpinBox()
        self.active_threshold_spin.setRange(100, 2000)
        self.active_threshold_spin.setSuffix(" ms")
        self.active_threshold_spin.setValue(500)
        self.active_threshold_spin.setToolTip(
            "For 'Active Time' method: Maximum gap between keystrokes\n"
            "to count as active typing time."
        )
        burst_layout.addRow("Active time threshold:", self.active_threshold_spin)

        self.high_score_duration_spin = QSpinBox()
        self.high_score_duration_spin.setRange(5000, 60000)
        self.high_score_duration_spin.setSuffix(" ms")
        self.high_score_duration_spin.setValue(10000)
        self.high_score_duration_spin.setToolTip(
            "Minimum burst duration to qualify for high score notifications"
        )
        burst_layout.addRow("High score min duration:", self.high_score_duration_spin)

        self.min_key_count_spin = QSpinBox()
        self.min_key_count_spin.setRange(1, 100)
        self.min_key_count_spin.setSuffix(" keys")
        self.min_key_count_spin.setValue(10)
        self.min_key_count_spin.setToolTip(
            "Minimum keystrokes required for a burst to be recorded.\n"
            "Prevents keyboard shortcuts and brief typing from being counted."
        )
        burst_layout.addRow("Min burst key count:", self.min_key_count_spin)

        self.min_burst_duration_spin = QSpinBox()
        self.min_burst_duration_spin.setRange(1000, 30000)
        self.min_burst_duration_spin.setSuffix(" ms")
        self.min_burst_duration_spin.setValue(5000)
        self.min_burst_duration_spin.setToolTip(
            "Minimum duration for a burst to be recorded.\n"
            "Prevents very short typing sessions from being counted."
        )
        burst_layout.addRow("Min burst duration:", self.min_burst_duration_spin)

        burst_group.setLayout(burst_layout)
        layout.addWidget(burst_group)

        keyboard_group = QGroupBox("Keyboard")
        keyboard_layout = QFormLayout()

        self.keyboard_layout_combo = QComboBox()
        self.keyboard_layout_combo.addItem("Auto-detect", "auto")
        self.keyboard_layout_combo.addItem("US (QWERTY)", "us")
        self.keyboard_layout_combo.addItem("German (QWERTZ)", "de")
        keyboard_layout.addRow("Layout:", self.keyboard_layout_combo)

        keyboard_group.setLayout(keyboard_layout)
        layout.addWidget(keyboard_group)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def create_notification_tab(self) -> QWidget:
        """Create notification settings tab."""
        widget = QWidget()
        layout = QVBoxLayout()

        enabled_group = QGroupBox("Notification Settings")
        enabled_layout = QFormLayout()

        self.notifications_check = QCheckBox("Enable notifications")
        self.notifications_check.setChecked(True)
        enabled_layout.addRow(self.notifications_check)

        self.exceptional_wpm_spin = QDoubleSpinBox()
        self.exceptional_wpm_spin.setRange(50, 300)
        self.exceptional_wpm_spin.setDecimals(1)
        self.exceptional_wpm_spin.setSuffix(" WPM")
        self.exceptional_wpm_spin.setValue(120)
        enabled_layout.addRow(
            "Exceptional burst WPM threshold:", self.exceptional_wpm_spin
        )

        self.notification_min_burst_spin = QSpinBox()
        self.notification_min_burst_spin.setRange(1, 60)
        self.notification_min_burst_spin.setSuffix(" s")
        self.notification_min_burst_spin.setValue(10)
        enabled_layout.addRow(
            "Minimum burst duration for notification:", self.notification_min_burst_spin
        )

        self.notification_threshold_days_spin = QSpinBox()
        self.notification_threshold_days_spin.setRange(7, 365)
        self.notification_threshold_days_spin.setSuffix(" days")
        self.notification_threshold_days_spin.setValue(30)
        enabled_layout.addRow(
            "Threshold calculation lookback period:",
            self.notification_threshold_days_spin,
        )

        self.notification_threshold_update_spin = QSpinBox()
        self.notification_threshold_update_spin.setRange(60, 3600)
        self.notification_threshold_update_spin.setSuffix(" s")
        self.notification_threshold_update_spin.setValue(300)
        enabled_layout.addRow(
            "Threshold update interval:", self.notification_threshold_update_spin
        )

        enabled_group.setLayout(enabled_layout)
        layout.addWidget(enabled_group)

        time_group = QGroupBox("Daily Summary Time")
        time_layout = QFormLayout()

        self.notification_hour_spin = QSpinBox()
        self.notification_hour_spin.setRange(0, 23)
        self.notification_hour_spin.setSuffix(":00")
        self.notification_hour_spin.setValue(18)
        time_layout.addRow("Hour:", self.notification_hour_spin)

        time_group.setLayout(time_layout)
        layout.addWidget(time_group)

        info_label = QLabel(
            "📊 Daily summary will show total keystrokes, "
            "typing time, average WPM, and slowest key."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(info_label)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def create_data_tab(self) -> QWidget:
        """Create data management tab."""
        widget = QWidget()
        layout = QVBoxLayout()

        display_group = QGroupBox("Statistics Display")
        display_layout = QFormLayout()

        self.slowest_keys_spin = QSpinBox()
        self.slowest_keys_spin.setRange(1, 50)
        self.slowest_keys_spin.setSuffix(" keys")
        self.slowest_keys_spin.setValue(10)
        display_layout.addRow("Show slowest keys:", self.slowest_keys_spin)

        display_group.setLayout(display_layout)
        layout.addWidget(display_group)

        retention_group = QGroupBox("Data Retention")
        retention_layout = QFormLayout()

        self.retention_combo = QComboBox()
        self.retention_combo.addItem("Keep forever", -1)
        self.retention_combo.addItem("30 days", 30)
        self.retention_combo.addItem("60 days", 60)
        self.retention_combo.addItem("90 days", 90)
        self.retention_combo.addItem("180 days", 180)
        self.retention_combo.addItem("365 days", 365)
        retention_layout.addRow("Keep data for:", self.retention_combo)

        retention_group.setLayout(retention_layout)
        layout.addWidget(retention_group)

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

        lang_label = QLabel("Select languages to validate:")
        lang_layout.addWidget(lang_label)

        self.language_list_widget = QListWidget()
        self.language_list_widget.setMaximumHeight(120)
        lang_layout.addWidget(self.language_list_widget)

        # Scan button
        scan_button_layout = QHBoxLayout()
        self.rescan_button = QPushButton("Rescan Dictionaries")
        self.rescan_button.clicked.connect(self.rescan_dictionaries)
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

    def rescan_dictionaries(self) -> None:
        """Rescan system for available dictionaries."""
        try:
            from utils.dict_detector import DictionaryDetector

            available = DictionaryDetector.detect_available()

            # Enable checkbox selection
            self.language_list_widget.clear()
            self.language_list_widget.setSelectionMode(QListWidget.NoSelection)

            # Get current selections from settings if available
            current_selections = self.current_settings.get("enabled_dictionaries", "")
            selected_set = set(current_selections.split(",")) if current_selections else set()

            for dict_info in available:
                item_text = f"{dict_info.language_name}"
                if dict_info.variant:
                    item_text += f" ({dict_info.variant})"

                # Create item with checkbox
                from PyQt5.QtWidgets import QListWidgetItem
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
                else:
                    # Default selections
                    if (dict_info.language_code == "de" and dict_info.variant and "reform" in dict_info.variant):
                        should_check = True
                    elif (dict_info.language_code == "en" and dict_info.variant and "American" in dict_info.variant):
                        should_check = True

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
            self.current_settings.get("high_score_min_duration_ms", 10000) // 1000
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
        self.notifications_check.setChecked(
            self.current_settings.get("notifications_enabled", True)
        )
        self.exceptional_wpm_spin.setValue(
            self.current_settings.get("exceptional_wpm_threshold", 120)
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
        self.slowest_keys_spin.setValue(
            self.current_settings.get("slowest_keys_count", 10)
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
            "high_score_min_duration_ms": str(
                self.high_score_duration_spin.value() * 1000
            ),
            "min_burst_key_count": str(self.min_key_count_spin.value()),
            "min_burst_duration_ms": str(self.min_burst_duration_spin.value()),
            "keyboard_layout": self.keyboard_layout_combo.currentData().lower(),
            "notifications_enabled": str(self.notifications_check.isChecked()),
            "exceptional_wpm_threshold": str(int(self.exceptional_wpm_spin.value())),
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
            "slowest_keys_count": str(self.slowest_keys_spin.value()),
            "data_retention_days": str(self.retention_combo.currentData()),
            "dictionary_mode": "validate"
            if self.validate_mode_radio.isChecked()
            else "accept_all",
            "enabled_languages": enabled_langs_str,
            "enabled_dictionaries": enabled_dicts_str,
            "custom_dict_paths": "",
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
        from PyQt5.QtWidgets import QMessageBox

        reply = QMessageBox.question(
            self,
            "Clear All Data",
            "Are you sure you want to delete all typing data?\n\n"
            "This action cannot be undone!",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            self.settings = self.get_settings()
            self.settings["__clear_database__"] = True
            self.accept()
