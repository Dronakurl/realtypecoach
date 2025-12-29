"""Statistics panel for RealTypeCoach."""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QLabel, QTabWidget,
                               QTableWidget, QTableWidgetItem, QHeaderView,
                               QPushButton, QHBoxLayout, QApplication)
from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtGui import QIcon, QPixmap, QImage, QPainter, QColor, QPalette
from typing import List, Tuple


class StatsPanel(QWidget):
    """Real-time statistics display panel."""

    settings_requested = pyqtSignal()

    def __init__(self):
        """Initialize statistics panel."""
        super().__init__()
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

    def init_ui(self) -> None:
        """Initialize user interface."""
        layout = QVBoxLayout()

        # Title
        self.title_label = QLabel("⌨ RealTypeCoach Statistics")
        self.title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(self.title_label)

        # Settings button
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        settings_btn = QPushButton("⚙️ Settings")
        settings_btn.clicked.connect(self.settings_requested.emit)
        button_layout.addWidget(settings_btn)

        layout.addLayout(button_layout)

        # Create tab widget
        tab_widget = QTabWidget()
        # Set larger icon size for better visibility
        tab_widget.setIconSize(QSize(24, 24))

        # Tab 1: Overview (WPM + Today's Stats)
        overview_tab = QWidget()
        overview_layout = QVBoxLayout(overview_tab)

        self.wpm_label = QLabel("Current WPM: --")
        self.wpm_label.setStyleSheet("font-size: 24px; color: #3daee9; font-weight: bold;")
        overview_layout.addWidget(self.wpm_label)

        self.burst_wpm_label = QLabel("Burst WPM: --")
        self.burst_wpm_label.setStyleSheet("font-size: 16px;")
        overview_layout.addWidget(self.burst_wpm_label)

        self.personal_best_label = QLabel("Personal Best Today: --")
        self.personal_best_label.setStyleSheet("font-size: 16px; color: #ff6b6b;")
        overview_layout.addWidget(self.personal_best_label)

        overview_layout.addSpacing(20)

        self.keystrokes_label = QLabel("Keystrokes: 0")
        self.keystrokes_label.setStyleSheet("font-size: 12px;")
        overview_layout.addWidget(self.keystrokes_label)

        self.bursts_label = QLabel("Bursts: 0")
        self.bursts_label.setStyleSheet("font-size: 12px;")
        overview_layout.addWidget(self.bursts_label)

        self.typing_time_label = QLabel("Typing time: 0m 0s")
        self.typing_time_label.setStyleSheet("font-size: 12px;")
        overview_layout.addWidget(self.typing_time_label)

        overview_layout.addStretch()
        tab_widget.addTab(overview_tab, self._create_palette_aware_icon("view-refresh"), "Overview")

        # Tab 2: Keys
        keys_tab = QWidget()
        keys_layout = QVBoxLayout(keys_tab)

        self.slowest_title = QLabel("🐌 Slowest Letter Keys (Top 10)")
        self.slowest_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        keys_layout.addWidget(self.slowest_title)

        self.slowest_table = QTableWidget()
        self.slowest_table.setColumnCount(3)
        self.slowest_table.setHorizontalHeaderLabels(["Rank", "Key", "WPM"])
        self.slowest_table.verticalHeader().setVisible(False)
        self.slowest_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.slowest_table.setRowCount(10)
        for i in range(10):
            self.slowest_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.slowest_table.setItem(i, 1, QTableWidgetItem("--"))
            self.slowest_table.setItem(i, 2, QTableWidgetItem("--"))
        keys_layout.addWidget(self.slowest_table)

        keys_layout.addSpacing(10)

        self.fastest_title = QLabel("⚡ Fastest Letter Keys (Top 10)")
        self.fastest_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        keys_layout.addWidget(self.fastest_title)

        self.fastest_table = QTableWidget()
        self.fastest_table.setColumnCount(3)
        self.fastest_table.setHorizontalHeaderLabels(["Rank", "Key", "WPM"])
        self.fastest_table.verticalHeader().setVisible(False)
        self.fastest_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.fastest_table.setRowCount(10)
        for i in range(10):
            self.fastest_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.fastest_table.setItem(i, 1, QTableWidgetItem("--"))
            self.fastest_table.setItem(i, 2, QTableWidgetItem("--"))
        keys_layout.addWidget(self.fastest_table)

        keys_layout.addStretch()
        tab_widget.addTab(keys_tab, self._create_palette_aware_icon("input-keyboard"), "Keys")

        # Tab 3: Words
        words_tab = QWidget()
        words_layout = QVBoxLayout(words_tab)

        self.hardest_words_title = QLabel("🐢 Hardest Words (All Time)")
        self.hardest_words_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        words_layout.addWidget(self.hardest_words_title)

        self.hardest_words_table = QTableWidget()
        self.hardest_words_table.setColumnCount(4)
        self.hardest_words_table.setHorizontalHeaderLabels(["Rank", "Word", "WPM", "Duration (ms)"])
        self.hardest_words_table.verticalHeader().setVisible(False)
        self.hardest_words_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.hardest_words_table.setRowCount(10)
        for i in range(10):
            self.hardest_words_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.hardest_words_table.setItem(i, 1, QTableWidgetItem("--"))
            self.hardest_words_table.setItem(i, 2, QTableWidgetItem("--"))
            self.hardest_words_table.setItem(i, 3, QTableWidgetItem("--"))
        words_layout.addWidget(self.hardest_words_table)

        words_layout.addSpacing(10)

        self.fastest_words_title = QLabel("⚡ Fastest Words (All Time)")
        self.fastest_words_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        words_layout.addWidget(self.fastest_words_title)

        self.fastest_words_table = QTableWidget()
        self.fastest_words_table.setColumnCount(4)
        self.fastest_words_table.setHorizontalHeaderLabels(["Rank", "Word", "WPM", "Duration (ms)"])
        self.fastest_words_table.verticalHeader().setVisible(False)
        self.fastest_words_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.fastest_words_table.setRowCount(10)
        for i in range(10):
            self.fastest_words_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.fastest_words_table.setItem(i, 1, QTableWidgetItem("--"))
            self.fastest_words_table.setItem(i, 2, QTableWidgetItem("--"))
            self.fastest_words_table.setItem(i, 3, QTableWidgetItem("--"))
        words_layout.addWidget(self.fastest_words_table)

        words_layout.addStretch()
        tab_widget.addTab(words_tab, self._create_palette_aware_icon("text-x-generic"), "Words")

        # Tab 4: Trends (NEW)
        trends_tab = QWidget()
        trends_layout = QVBoxLayout(trends_tab)

        from ui.wpm_graph import WPMTimeSeriesGraph

        self.wpm_graph = WPMTimeSeriesGraph()
        trends_layout.addWidget(self.wpm_graph)

        tab_widget.addTab(trends_tab, self._create_palette_aware_icon("go-up"), "Trends")

        layout.addWidget(tab_widget)
        self.setLayout(layout)

        # Set default window size (wider for better table display)
        self.resize(700, 500)

    def update_wpm(self, current_wpm: float, burst_wpm: float,
                   personal_best: float) -> None:
        """Update WPM display.

        Args:
            current_wpm: Current overall WPM
            burst_wpm: Current burst WPM
            personal_best: Personal best WPM today
        """
        self.wpm_label.setText(f"Current WPM: {current_wpm:.1f}")
        self.burst_wpm_label.setText(f"Burst WPM: {burst_wpm:.1f}")

        if personal_best > 0:
            self.personal_best_label.setText(f"Personal Best Today: {personal_best:.1f}")
        else:
            self.personal_best_label.setText("Personal Best Today: --")

    def update_slowest_keys(self, slowest_keys: List[Tuple[int, str, float]]) -> None:
        """Update slowest keys display.

        Args:
            slowest_keys: List of (keycode, key_name, avg_time_ms) tuples
        """
        for i, (keycode, key_name, avg_time) in enumerate(slowest_keys):
            projected_wpm = 12000 / avg_time if avg_time > 0 else 0
            self.slowest_table.setItem(i, 1, QTableWidgetItem(key_name))
            self.slowest_table.setItem(i, 2, QTableWidgetItem(f"{projected_wpm:.1f}"))

        for i in range(len(slowest_keys), 10):
            self.slowest_table.setItem(i, 1, QTableWidgetItem("--"))
            self.slowest_table.setItem(i, 2, QTableWidgetItem("--"))

    def update_fastest_keys(self, fastest_keys: List[Tuple[int, str, float]]) -> None:
        """Update fastest keys display.

        Args:
            fastest_keys: List of (keycode, key_name, avg_time_ms) tuples
        """
        for i, (keycode, key_name, avg_time) in enumerate(fastest_keys):
            projected_wpm = 12000 / avg_time if avg_time > 0 else 0
            self.fastest_table.setItem(i, 1, QTableWidgetItem(key_name))
            self.fastest_table.setItem(i, 2, QTableWidgetItem(f"{projected_wpm:.1f}"))

        for i in range(len(fastest_keys), 10):
            self.fastest_table.setItem(i, 1, QTableWidgetItem("--"))
            self.fastest_table.setItem(i, 2, QTableWidgetItem("--"))

    def update_today_stats(self, keystrokes: int, bursts: int,
                         typing_sec: float) -> None:
        """Update today's statistics.

        Args:
            keystrokes: Total keystrokes today
            bursts: Total bursts today
            typing_sec: Total typing time in seconds
        """
        self.keystrokes_label.setText(f"Keystrokes: {keystrokes:,}")
        self.bursts_label.setText(f"Bursts: {bursts:,}")

        hours = typing_sec // 3600
        minutes = (typing_sec % 3600) // 60
        seconds = typing_sec % 60

        if hours > 0:
            time_str = f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            time_str = f"{minutes}m {seconds}s"
        else:
            time_str = f"{seconds}s"

        self.typing_time_label.setText(f"Typing time: {time_str}")

    def update_hardest_words(self, words: List[Tuple[str, float, int, int]]) -> None:
        """Update hardest words display.

        Args:
            words: List of (word, avg_speed_ms_per_letter, duration_ms, num_letters) tuples
        """
        for i, (word, speed_ms_per_letter, duration_ms, num_letters) in enumerate(words):
            projected_wpm = 12000 / speed_ms_per_letter if speed_ms_per_letter > 0 else 0
            self.hardest_words_table.setItem(i, 1, QTableWidgetItem(word))
            self.hardest_words_table.setItem(i, 2, QTableWidgetItem(f"{projected_wpm:.1f}"))
            self.hardest_words_table.setItem(i, 3, QTableWidgetItem(str(duration_ms)))

        for i in range(len(words), 10):
            self.hardest_words_table.setItem(i, 1, QTableWidgetItem("--"))
            self.hardest_words_table.setItem(i, 2, QTableWidgetItem("--"))
            self.hardest_words_table.setItem(i, 3, QTableWidgetItem("--"))

    def update_fastest_words(self, words: List[Tuple[str, float, int, int]]) -> None:
        """Update fastest words display.

        Args:
            words: List of (word, avg_speed_ms_per_letter, duration_ms, num_letters) tuples
        """
        for i, (word, speed_ms_per_letter, duration_ms, num_letters) in enumerate(words):
            projected_wpm = 12000 / speed_ms_per_letter if speed_ms_per_letter > 0 else 0
            self.fastest_words_table.setItem(i, 1, QTableWidgetItem(word))
            self.fastest_words_table.setItem(i, 2, QTableWidgetItem(f"{projected_wpm:.1f}"))
            self.fastest_words_table.setItem(i, 3, QTableWidgetItem(str(duration_ms)))

        for i in range(len(words), 10):
            self.fastest_words_table.setItem(i, 1, QTableWidgetItem("--"))
            self.fastest_words_table.setItem(i, 2, QTableWidgetItem("--"))
            self.fastest_words_table.setItem(i, 3, QTableWidgetItem("--"))

    def set_trend_data_callback(self, callback) -> None:
        """Set callback for requesting trend data.

        Args:
            callback: Function to call when new data is needed
        """
        self.wpm_graph.set_data_callback(callback)

    def update_trend_graph(self, data: List[Tuple[int, float]]) -> None:
        """Update trend graph with new data.

        Args:
            data: List of (timestamp_ms, avg_wpm) tuples
        """
        self.wpm_graph.update_graph(data)
