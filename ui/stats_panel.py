"""Statistics panel for RealTypeCoach."""

from typing import List, Tuple

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPalette, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.models import KeyPerformance, TypingTimeDataPoint, WordStatisticsLite


class StatsPanel(QWidget):
    """Real-time statistics display panel."""

    settings_requested = Signal()

    def __init__(self, icon_path: str = None):
        """Initialize statistics panel.

        Args:
            icon_path: Optional path to the project logo icon
        """
        super().__init__()
        self.icon_path = icon_path
        self.slowest_keys_count = 10
        self._clipboard = QApplication.clipboard()
        self._trend_data_loaded = False
        self._typing_time_data_loaded = False
        self._histogram_data_loaded = False
        self._trend_data_callback = None
        self._typing_time_data_callback = None
        self._histogram_data_callback = None
        self.init_ui()

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

    def _create_metric_card(self, label_text: str, color: str) -> QGroupBox:
        """Create a large metric display card.

        Args:
            label_text: Label for the metric
            color: Accent color for the metric value

        Returns:
            QGroupBox configured as a metric card
        """
        card = QGroupBox()
        card.setStyleSheet("QGroupBox { border: none; }")
        layout = QVBoxLayout()
        layout.setSpacing(8)

        # Label
        label = QLabel(label_text)
        label.setStyleSheet("font-size: 16px; font-weight: bold; color: #666;")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)

        # Value
        value = QLabel("--")
        value.setStyleSheet(f"font-size: 40px; font-weight: bold; color: {color};")
        value.setAlignment(Qt.AlignCenter)
        layout.addWidget(value)

        # Subtitle
        subtitle = QLabel("")
        subtitle.setStyleSheet("font-size: 14px; color: #888;")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)

        card.setLayout(layout)

        # Store references to update later
        if "Current Burst" in label_text:
            self.burst_wpm_value_label = value
            self.burst_wpm_subtitle_label = subtitle
        elif "Long-term Average" in label_text:
            self.avg_wpm_value_label = value
            self.avg_wpm_subtitle_label = subtitle
        elif "Hardest Letter" in label_text:
            self.worst_letter_value_label = value
            self.worst_letter_subtitle_label = subtitle
        elif "Hardest Word" in label_text:
            self.hardest_word_value_label = value
            self.hardest_word_subtitle_label = subtitle
        elif "Fastest Word" in label_text:
            self.fastest_word_value_label = value
            self.fastest_word_subtitle_label = subtitle
        elif "Keystrokes" in label_text:
            self.keystrokes_bursts_value_label = value
            self.keystrokes_bursts_subtitle_label = subtitle
        elif "Typing Time" in label_text:
            self.typing_time_value_label = value
            self.typing_time_subtitle_label = subtitle
        elif "Avg Burst Time" in label_text:
            self.avg_burst_time_value_label = value
            self.avg_burst_time_subtitle_label = subtitle

        return card

    def init_ui(self) -> None:
        """Initialize user interface."""
        # Enable font antialiasing
        self.setAttribute(Qt.WA_StyledBackground)
        font = QApplication.font()
        font.setStyleStrategy(QFont.PreferAntialias)
        self.setFont(font)

        layout = QVBoxLayout()

        # Header with logo and title
        header_layout = QHBoxLayout()

        # Logo
        if self.icon_path:
            from PySide6.QtSvgWidgets import QSvgWidget

            self.logo_widget = QSvgWidget(self.icon_path)
            self.logo_widget.setFixedSize(48, 48)
            header_layout.addWidget(self.logo_widget)

        # Title
        self.title_label = QLabel("Statistics")
        self.title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()

        # Settings button
        settings_btn = QPushButton("⚙️ Settings")
        settings_btn.clicked.connect(self.settings_requested.emit)
        header_layout.addWidget(settings_btn)

        layout.addLayout(header_layout)

        # Create tab widget
        tab_widget = QTabWidget()
        # Set larger icon size for better visibility
        tab_widget.setIconSize(QSize(24, 24))

        # Tab 1: Overview (WPM + Today's Stats)
        overview_tab = QWidget()
        overview_layout = QVBoxLayout(overview_tab)
        overview_layout.setSpacing(20)

        # Performance Dashboard with large metric cards
        dashboard_widget = QWidget()
        dashboard_layout = QVBoxLayout(dashboard_widget)
        dashboard_layout.setSpacing(15)

        # Row 1: WPM metrics
        first_row = QHBoxLayout()
        first_row.setSpacing(30)

        # Current Burst WPM Card
        burst_wpm_card = self._create_metric_card("Current Burst WPM", "#3daee9")
        first_row.addWidget(burst_wpm_card)

        # Long-term Average WPM Card
        avg_wpm_card = self._create_metric_card("Long-term Average WPM", "#4caf50")
        first_row.addWidget(avg_wpm_card)

        dashboard_layout.addLayout(first_row)

        # Row 2: Hardest and Fastest Words
        second_row = QHBoxLayout()
        second_row.setSpacing(30)

        # Hardest Word Card
        hardest_word_card = self._create_metric_card("Hardest Word", "#e67e22")
        second_row.addWidget(hardest_word_card)

        # Fastest Word Card
        fastest_word_card = self._create_metric_card("Fastest Word", "#2ecc71")
        second_row.addWidget(fastest_word_card)

        dashboard_layout.addLayout(second_row)

        # Row 3: Totals
        third_row = QHBoxLayout()
        third_row.setSpacing(30)

        # Keystrokes & Bursts Card
        keystrokes_bursts_card = self._create_metric_card(
            "Keystrokes & Bursts", "#3498db"
        )
        third_row.addWidget(keystrokes_bursts_card)

        # Typing Time Card
        typing_time_card = self._create_metric_card("Typing Time", "#9b59b6")
        third_row.addWidget(typing_time_card)

        dashboard_layout.addLayout(third_row)

        # Row 4: Hardest Letter and Avg Burst Time
        fourth_row = QHBoxLayout()
        fourth_row.setSpacing(30)

        # Worst Letter Card
        worst_letter_card = self._create_metric_card("Hardest Letter", "#ff6b6b")
        fourth_row.addWidget(worst_letter_card)

        # Avg Burst Time Card
        avg_burst_time_card = self._create_metric_card("Avg Burst Time", "#1abc9c")
        fourth_row.addWidget(avg_burst_time_card)

        dashboard_layout.addLayout(fourth_row)

        overview_layout.addWidget(dashboard_widget)

        overview_layout.addStretch()
        tab_widget.addTab(
            overview_tab, self._create_palette_aware_icon("view-refresh"), "Overview"
        )

        # Tab 2: Keys
        keys_tab = QWidget()
        keys_layout = QHBoxLayout(keys_tab)

        # Fastest Letter Keys (Left)
        fastest_keys_widget = QWidget()
        fastest_keys_layout = QVBoxLayout(fastest_keys_widget)
        self.fastest_title = QLabel(
            f"⚡ Fastest Letter Keys (Top {self.slowest_keys_count})"
        )
        self.fastest_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        fastest_keys_layout.addWidget(self.fastest_title)

        self.fastest_table = QTableWidget()
        self.fastest_table.setFont(font)
        self.fastest_table.setColumnCount(3)
        self.fastest_table.setHorizontalHeaderLabels(["Key", "WPM", "Rank"])
        self.fastest_table.verticalHeader().setVisible(False)
        self.fastest_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.fastest_table.setRowCount(self.slowest_keys_count)
        for i in range(self.slowest_keys_count):
            self.fastest_table.setItem(i, 0, QTableWidgetItem("--"))
            self.fastest_table.setItem(i, 1, QTableWidgetItem("--"))
            self.fastest_table.setItem(i, 2, QTableWidgetItem("--"))
        fastest_keys_layout.addWidget(self.fastest_table)

        keys_layout.addWidget(fastest_keys_widget)

        # Slowest Letter Keys (Right)
        slowest_keys_widget = QWidget()
        slowest_keys_layout = QVBoxLayout(slowest_keys_widget)
        self.slowest_title = QLabel(
            f"🐌 Slowest Letter Keys (Top {self.slowest_keys_count})"
        )
        self.slowest_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        slowest_keys_layout.addWidget(self.slowest_title)

        self.slowest_table = QTableWidget()
        self.slowest_table.setFont(font)
        self.slowest_table.setColumnCount(3)
        self.slowest_table.setHorizontalHeaderLabels(["Key", "WPM", "Rank"])
        self.slowest_table.verticalHeader().setVisible(False)
        self.slowest_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.slowest_table.setRowCount(self.slowest_keys_count)
        for i in range(self.slowest_keys_count):
            self.slowest_table.setItem(i, 0, QTableWidgetItem("--"))
            self.slowest_table.setItem(i, 1, QTableWidgetItem("--"))
            self.slowest_table.setItem(i, 2, QTableWidgetItem("--"))
        slowest_keys_layout.addWidget(self.slowest_table)

        keys_layout.addWidget(slowest_keys_widget)

        tab_widget.addTab(
            keys_tab, self._create_palette_aware_icon("input-keyboard"), "Keys"
        )

        # Tab 3: Words
        words_tab = QWidget()
        words_layout = QHBoxLayout(words_tab)

        # Fastest Words (Left)
        fastest_words_widget = QWidget()
        fastest_words_layout = QVBoxLayout(fastest_words_widget)
        self.fastest_words_title = QLabel("⚡ Fastest Words (All Time)")
        self.fastest_words_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        fastest_words_layout.addWidget(self.fastest_words_title)

        self.fastest_words_table = QTableWidget()
        self.fastest_words_table.setFont(font)
        self.fastest_words_table.setColumnCount(3)
        self.fastest_words_table.setHorizontalHeaderLabels(["Word", "WPM", "Rank"])
        self.fastest_words_table.verticalHeader().setVisible(False)
        self.fastest_words_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        self.fastest_words_table.setRowCount(10)
        for i in range(10):
            self.fastest_words_table.setItem(i, 0, QTableWidgetItem("--"))
            self.fastest_words_table.setItem(i, 1, QTableWidgetItem("--"))
            self.fastest_words_table.setItem(i, 2, QTableWidgetItem("--"))
        fastest_words_layout.addWidget(self.fastest_words_table)

        words_layout.addWidget(fastest_words_widget)

        # Hardest Words (Right)
        hardest_words_widget = QWidget()
        hardest_words_layout = QVBoxLayout(hardest_words_widget)
        self.hardest_words_title = QLabel("🐢 Hardest Words (All Time)")
        self.hardest_words_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        hardest_words_layout.addWidget(self.hardest_words_title)

        self.hardest_words_table = QTableWidget()
        self.hardest_words_table.setFont(font)
        self.hardest_words_table.setColumnCount(3)
        self.hardest_words_table.setHorizontalHeaderLabels(["Word", "WPM", "Rank"])
        self.hardest_words_table.verticalHeader().setVisible(False)
        self.hardest_words_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        self.hardest_words_table.setRowCount(10)
        for i in range(10):
            self.hardest_words_table.setItem(i, 0, QTableWidgetItem("--"))
            self.hardest_words_table.setItem(i, 1, QTableWidgetItem("--"))
            self.hardest_words_table.setItem(i, 2, QTableWidgetItem("--"))
        hardest_words_layout.addWidget(self.hardest_words_table)

        # Controls row for clipboard functionality
        controls_layout = QHBoxLayout()

        count_label = QLabel("Copy:")
        count_label.setStyleSheet("font-size: 12px; color: #666;")
        controls_layout.addWidget(count_label)

        self.hardest_words_count_combo = QComboBox()
        self.hardest_words_count_combo.addItem("10", 10)
        self.hardest_words_count_combo.addItem("25", 25)
        self.hardest_words_count_combo.addItem("50", 50)
        self.hardest_words_count_combo.addItem("75", 75)
        self.hardest_words_count_combo.addItem("100", 100)
        self.hardest_words_count_combo.setCurrentIndex(0)  # Default to 10
        self.hardest_words_count_combo.setMaximumWidth(80)
        controls_layout.addWidget(self.hardest_words_count_combo)

        self.copy_hardest_words_btn = QPushButton("📋 Copy Words")
        self.copy_hardest_words_btn.setStyleSheet("QPushButton { padding: 4px 12px; }")
        self.copy_hardest_words_btn.clicked.connect(
            self.copy_hardest_words_to_clipboard
        )
        controls_layout.addWidget(self.copy_hardest_words_btn)

        controls_layout.addStretch()
        hardest_words_layout.addLayout(controls_layout)

        words_layout.addWidget(hardest_words_widget)

        tab_widget.addTab(
            words_tab, self._create_palette_aware_icon("text-x-generic"), "Words"
        )

        # Tab 4: Trends (NEW)
        trends_tab = QWidget()
        trends_layout = QVBoxLayout(trends_tab)

        from ui.wpm_graph import WPMTimeSeriesGraph

        self.wpm_graph = WPMTimeSeriesGraph()
        trends_layout.addWidget(self.wpm_graph)

        tab_widget.addTab(
            trends_tab, self._create_palette_aware_icon("go-up"), "Trends"
        )

        # Tab 5: Typing Time
        typing_time_tab = QWidget()
        typing_time_layout = QVBoxLayout(typing_time_tab)

        from ui.typing_time_graph import TypingTimeGraph

        self.typing_time_graph = TypingTimeGraph()
        typing_time_layout.addWidget(self.typing_time_graph)

        tab_widget.addTab(
            typing_time_tab,
            self._create_palette_aware_icon("x-office-calendar"),
            "Typing Time",
        )

        # Tab 6: Burst Speed Distribution
        histogram_tab = QWidget()
        histogram_layout = QVBoxLayout(histogram_tab)

        from ui.burst_histogram import BurstSpeedHistogram

        self.burst_histogram = BurstSpeedHistogram()
        histogram_layout.addWidget(self.burst_histogram)

        tab_widget.addTab(
            histogram_tab,
            self._create_palette_aware_icon("view-statistics"),
            "Burst Speeds",
        )

        layout.addWidget(tab_widget)
        self.tab_widget = tab_widget
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        self.setLayout(layout)

        # Set default window size (wider for better table display)
        self.resize(700, 500)

    def update_wpm(
        self,
        burst_wpm: float,
        today_best: float,
        long_term_avg: float,
        all_time_best: float,
    ) -> None:
        """Update WPM display.

        Args:
            burst_wpm: Current burst WPM
            today_best: Personal best WPM today
            long_term_avg: Long-term average WPM
            all_time_best: All-time best WPM
        """
        import logging

        log = logging.getLogger("realtypecoach.stats_panel")
        log.info(
            f"update_wpm() called: burst_wpm={burst_wpm:.1f}, visible={self.isVisible()}"
        )

        if not self.isVisible():
            log.info("update_wpm() - panel not visible, returning early")
            return

        # Update Current Burst WPM card
        if hasattr(self, "burst_wpm_value_label"):
            self.burst_wpm_value_label.setText(f"{burst_wpm:.1f}")
            if today_best > 0:
                self.burst_wpm_subtitle_label.setText(f"today's best: {today_best:.1f}")
            else:
                self.burst_wpm_subtitle_label.setText("today's best: --")

        # Update Long-term Average WPM card
        if hasattr(self, "avg_wpm_value_label"):
            if long_term_avg is not None and long_term_avg > 0:
                self.avg_wpm_value_label.setText(f"{long_term_avg:.1f}")
            else:
                self.avg_wpm_value_label.setText("--")

            if all_time_best is not None and all_time_best > 0:
                self.avg_wpm_subtitle_label.setText(
                    f"all-time best: {all_time_best:.1f}"
                )
            else:
                self.avg_wpm_subtitle_label.setText("all-time best: --")

    def update_slowest_keys(self, slowest_keys: List[KeyPerformance]) -> None:
        """Update slowest keys display.

        Args:
            slowest_keys: List of KeyPerformance models
        """
        if not self.isVisible():
            return

        for i, key_perf in enumerate(slowest_keys):
            avg_time = key_perf.avg_press_time
            wpm = 12000 / avg_time if avg_time > 0 else 0
            self.slowest_table.setItem(i, 0, QTableWidgetItem(key_perf.key_name))
            self.slowest_table.setItem(i, 1, QTableWidgetItem(f"{wpm:.1f}"))
            self.slowest_table.setItem(
                i,
                2,
                QTableWidgetItem(str(key_perf.rank) if key_perf.rank > 0 else "--"),
            )

        for i in range(len(slowest_keys), self.slowest_keys_count):
            self.slowest_table.setItem(i, 0, QTableWidgetItem("--"))
            self.slowest_table.setItem(i, 1, QTableWidgetItem("--"))
            self.slowest_table.setItem(i, 2, QTableWidgetItem("--"))

    def update_fastest_keys(self, fastest_keys: List[KeyPerformance]) -> None:
        """Update fastest keys display.

        Args:
            fastest_keys: List of KeyPerformance models
        """
        if not self.isVisible():
            return

        for i, key_perf in enumerate(fastest_keys):
            avg_time = key_perf.avg_press_time
            wpm = 12000 / avg_time if avg_time > 0 else 0
            self.fastest_table.setItem(i, 0, QTableWidgetItem(key_perf.key_name))
            self.fastest_table.setItem(i, 1, QTableWidgetItem(f"{wpm:.1f}"))
            self.fastest_table.setItem(
                i,
                2,
                QTableWidgetItem(str(key_perf.rank) if key_perf.rank > 0 else "--"),
            )

        for i in range(len(fastest_keys), self.slowest_keys_count):
            self.fastest_table.setItem(i, 0, QTableWidgetItem("--"))
            self.fastest_table.setItem(i, 1, QTableWidgetItem("--"))
            self.fastest_table.setItem(i, 2, QTableWidgetItem("--"))

    def update_worst_letter(self, key_name: str, avg_time_ms: float) -> None:
        """Update hardest letter display.

        Args:
            key_name: Worst letter key name
            avg_time_ms: Average press time in milliseconds
        """
        if not self.isVisible():
            return

        if hasattr(self, "worst_letter_value_label"):
            if not key_name:
                self.worst_letter_value_label.setText("-")
                self.worst_letter_subtitle_label.setText("no data")
            else:
                self.worst_letter_value_label.setText(f"'{key_name}'")

                # Calculate equivalent WPM
                wpm = 12000 / avg_time_ms if avg_time_ms > 0 else 0
                self.worst_letter_subtitle_label.setText(f"{wpm:.0f} WPM")

    def update_worst_word(self, word_stat: WordStatisticsLite | None) -> None:
        """Update hardest word display.

        Args:
            word_stat: WordStatisticsLite model with hardest word data, or None if no data
        """
        if not self.isVisible():
            return

        if hasattr(self, "hardest_word_value_label"):
            if word_stat is None:
                self.hardest_word_value_label.setText("-")
                self.hardest_word_subtitle_label.setText("no data")
            else:
                self.hardest_word_value_label.setText(word_stat.word)

                # Calculate projected WPM
                wpm = (
                    12000 / word_stat.avg_speed_ms_per_letter
                    if word_stat.avg_speed_ms_per_letter > 0
                    else 0
                )
                self.hardest_word_subtitle_label.setText(f"{wpm:.0f} WPM")

    def update_fastest_word(self, word_stat: WordStatisticsLite | None) -> None:
        """Update fastest word display.

        Args:
            word_stat: WordStatisticsLite model with fastest word data, or None if no data
        """
        if not self.isVisible():
            return

        if hasattr(self, "fastest_word_value_label"):
            if word_stat is None:
                self.fastest_word_value_label.setText("-")
                self.fastest_word_subtitle_label.setText("no data")
            else:
                self.fastest_word_value_label.setText(word_stat.word)

                # Calculate projected WPM
                wpm = (
                    12000 / word_stat.avg_speed_ms_per_letter
                    if word_stat.avg_speed_ms_per_letter > 0
                    else 0
                )
                self.fastest_word_subtitle_label.setText(f"{wpm:.0f} WPM")

    def update_typing_time_display(self, today_sec: float, all_time_sec: float) -> None:
        """Update typing time display.

        Args:
            today_sec: Today's typing time in seconds
            all_time_sec: All-time typing time in seconds
        """
        if not self.isVisible():
            return

        if hasattr(self, "typing_time_value_label"):
            # Format today's typing time
            self.typing_time_value_label.setText(self._format_duration(today_sec))

            # Format all-time typing time
            self.typing_time_subtitle_label.setText(
                f"all-time: {self._format_duration(all_time_sec)}"
            )

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Format duration in seconds to human-readable string.

        Args:
            seconds: Duration in seconds

        Returns:
            Formatted duration string (e.g., "2d 5h 30m" or "45m 20s")
        """
        total_seconds = int(seconds)
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60

        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if secs > 0 or not parts:
            parts.append(f"{secs}s")

        return " ".join(parts)

    def update_keystrokes_bursts(
        self, keystrokes: int, bursts: int, today_keystrokes: int
    ) -> None:
        """Update all-time keystrokes and bursts display.

        Args:
            keystrokes: All-time total keystrokes
            bursts: All-time total bursts
            today_keystrokes: Today's keystrokes count
        """
        if not self.isVisible():
            return

        if hasattr(self, "keystrokes_bursts_value_label"):
            self.keystrokes_bursts_value_label.setText(
                self._format_large_number(keystrokes)
            )
            self.keystrokes_bursts_subtitle_label.setText(
                f"{self._format_large_number(bursts)} bursts • today: {self._format_large_number(today_keystrokes)}"
            )

    def update_avg_burst_duration(self, avg_ms: int, min_ms: int, max_ms: int) -> None:
        """Update average burst duration display.

        Args:
            avg_ms: Average burst duration in milliseconds
            min_ms: Minimum burst duration in milliseconds
            max_ms: Maximum burst duration in milliseconds
        """
        if not self.isVisible():
            return

        if hasattr(self, "avg_burst_time_value_label"):
            if avg_ms >= 1000:
                self.avg_burst_time_value_label.setText(f"{avg_ms / 1000:.1f}s")
            else:
                self.avg_burst_time_value_label.setText(f"{avg_ms}ms")

            # Format min/max as subtitle
            min_display = f"{min_ms / 1000:.1f}s" if min_ms >= 1000 else f"{min_ms}ms"
            max_display = f"{max_ms / 1000:.1f}s" if max_ms >= 1000 else f"{max_ms}ms"
            self.avg_burst_time_subtitle_label.setText(
                f"min: {min_display} • max: {max_display}"
            )

    @staticmethod
    def _format_large_number(count: int) -> str:
        """Format large numbers with K/M/B suffixes.

        Args:
            count: Number to format

        Returns:
            Formatted string (e.g., "1.5M", "234K")
        """
        if count >= 1_000_000_000:
            return f"{count / 1_000_000_000:.1f}B"
        elif count >= 1_000_000:
            return f"{count / 1_000_000:.1f}M"
        elif count >= 1_000:
            return f"{count / 1_000:.1f}K"
        else:
            return str(count)

    def update_hardest_words(self, words: List[WordStatisticsLite]) -> None:
        """Update hardest words display.

        Args:
            words: List of WordStatisticsLite models
        """
        if not self.isVisible():
            return

        for i, word_stat in enumerate(words):
            speed_ms_per_letter = word_stat.avg_speed_ms_per_letter
            projected_wpm = (
                12000 / speed_ms_per_letter if speed_ms_per_letter > 0 else 0
            )
            self.hardest_words_table.setItem(i, 0, QTableWidgetItem(word_stat.word))
            self.hardest_words_table.setItem(
                i, 1, QTableWidgetItem(f"{projected_wpm:.1f}")
            )
            self.hardest_words_table.setItem(
                i,
                2,
                QTableWidgetItem(str(word_stat.rank) if word_stat.rank > 0 else "--"),
            )

        for i in range(len(words), 10):
            self.hardest_words_table.setItem(i, 0, QTableWidgetItem("--"))
            self.hardest_words_table.setItem(i, 1, QTableWidgetItem("--"))
            self.hardest_words_table.setItem(i, 2, QTableWidgetItem("--"))

    def update_fastest_words(self, words: List[WordStatisticsLite]) -> None:
        """Update fastest words display.

        Args:
            words: List of WordStatisticsLite models
        """
        if not self.isVisible():
            return

        for i, word_stat in enumerate(words):
            speed_ms_per_letter = word_stat.avg_speed_ms_per_letter
            projected_wpm = (
                12000 / speed_ms_per_letter if speed_ms_per_letter > 0 else 0
            )
            self.fastest_words_table.setItem(i, 0, QTableWidgetItem(word_stat.word))
            self.fastest_words_table.setItem(
                i, 1, QTableWidgetItem(f"{projected_wpm:.1f}")
            )
            self.fastest_words_table.setItem(
                i,
                2,
                QTableWidgetItem(str(word_stat.rank) if word_stat.rank > 0 else "--"),
            )

        for i in range(len(words), 10):
            self.fastest_words_table.setItem(i, 0, QTableWidgetItem("--"))
            self.fastest_words_table.setItem(i, 1, QTableWidgetItem("--"))
            self.fastest_words_table.setItem(i, 2, QTableWidgetItem("--"))

    def set_trend_data_callback(self, callback) -> None:
        """Set callback for requesting trend data.

        Args:
            callback: Function to call when new data is needed
        """
        self._trend_data_callback = callback
        # Don't load immediately - wait for tab to be shown
        self.wpm_graph.set_data_callback(callback, load_immediately=False)

    def update_trend_graph(self, data: List[Tuple[int, float]]) -> None:
        """Update trend graph with new data.

        Args:
            data: List of (timestamp_ms, avg_wpm) tuples
        """
        self.wpm_graph.update_graph(data)

    def set_typing_time_data_callback(self, callback) -> None:
        """Set callback for requesting typing time data.

        Args:
            callback: Function to call when new data is needed
        """
        self._typing_time_data_callback = callback
        # Don't load immediately - wait for tab to be shown
        self.typing_time_graph.set_data_callback(callback, load_immediately=False)

    def update_typing_time_graph(self, data: List[TypingTimeDataPoint]) -> None:
        """Update typing time graph with new data.

        Args:
            data: List of TypingTimeDataPoint models
        """
        self.typing_time_graph.update_graph(data)

    def set_histogram_data_callback(self, callback) -> None:
        """Set callback for requesting histogram data.

        Args:
            callback: Function to call when new data is needed
        """
        self._histogram_data_callback = callback
        self.burst_histogram.set_data_callback(callback, load_immediately=False)

    def update_histogram_graph(self, data: List[Tuple[float, int]]) -> None:
        """Update histogram graph with new data.

        Args:
            data: List of (bin_center_wpm, count) tuples
        """
        self.burst_histogram.update_graph(data)

    def update_recent_bursts(
        self, recent_bursts: List[Tuple[int, float, int, int, int, int, str]]
    ) -> None:
        """Update recent bursts display.

        Args:
            recent_bursts: List of tuples with burst data
        """
        self.burst_histogram.update_recent_bursts(recent_bursts)

    def _on_tab_changed(self, index: int) -> None:
        """Handle tab change - load graph data lazily when tab is first viewed.

        Args:
            index: New tab index
        """
        # Tab 3 is Trends (index 3)
        if index == 3 and not self._trend_data_loaded:
            self._trend_data_loaded = True
            # Trigger data load via callback
            if self._trend_data_callback is not None:
                self._trend_data_callback(self.wpm_graph.current_window_size)

        # Tab 4 is Typing Time (index 4)
        if index == 4 and not self._typing_time_data_loaded:
            self._typing_time_data_loaded = True
            # Trigger data load via callback
            if self._typing_time_data_callback is not None:
                self._typing_time_data_callback(
                    self.typing_time_graph.current_granularity.value
                )

        # Tab 5 is Burst Speed Distribution (index 5)
        if index == 5 and not self._histogram_data_loaded:
            self._histogram_data_loaded = True
            if self._histogram_data_callback is not None:
                self._histogram_data_callback(self.burst_histogram.bin_count)

    def copy_hardest_words_to_clipboard(self) -> None:
        """Copy the n slowest words to clipboard."""
        count = self.hardest_words_count_combo.currentData()
        if hasattr(self, "_request_words_for_clipboard_callback"):
            # Store the callback temporarily and trigger fetch
            self._clipboard_callback = self._on_words_fetched_for_copy
            self._request_words_for_clipboard_callback(count)

    def _on_words_fetched_for_copy(self, words: List[WordStatisticsLite]) -> None:
        """Callback when words are fetched - copies to clipboard.

        Args:
            words: List of WordStatisticsLite models
        """
        if words:
            word_list = [w.word for w in words]
            clipboard_text = " ".join(word_list)
            # Use stored clipboard reference for Wayland compatibility
            from PySide6.QtGui import QClipboard

            # Try primary selection first (works better on some Wayland compositors)
            self._clipboard.setText(clipboard_text, QClipboard.Mode.Selection)
            # Also set clipboard for standard Ctrl+V
            self._clipboard.setText(clipboard_text, QClipboard.Mode.Clipboard)

            self._show_copy_notification(len(words))
        else:
            self._show_copy_notification(0)

    def _show_copy_notification(self, count: int) -> None:
        """Show notification after copy operation.

        Args:
            count: Number of words copied
        """
        if count > 0:
            message = f"Copied {count} words to clipboard"
        else:
            message = "No words available to copy"
        # Show tray notification through QApplication
        app = QApplication.instance()
        if app and hasattr(app, "tray_icon"):
            app.tray_icon.show_notification("Copy Words", message)

    def set_words_clipboard_callback(self, callback) -> None:
        """Set callback for fetching words for clipboard.

        Args:
            callback: Function to call with (count) parameter
        """
        self._request_words_for_clipboard_callback = callback

    def _on_clipboard_words_ready(self, words: List[WordStatisticsLite]) -> None:
        """Slot called when clipboard words are ready."""
        if hasattr(self, "_clipboard_callback"):
            self._clipboard_callback(words)
