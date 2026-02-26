"""Statistics panel for RealTypeCoach."""

import logging
import webbrowser

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPalette, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
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

from core.models import DigraphPerformance, KeyPerformance, TypingTimeDataPoint, WordStatisticsLite

log = logging.getLogger("realtypecoach.stats_panel")


class StatsPanel(QWidget):
    """Real-time statistics display panel."""

    settings_requested = Signal()
    visibility_changed = Signal(bool)  # Emitted when panel visibility changes

    def __init__(self, icon_path: str = None, config=None):
        """Initialize statistics panel.

        Args:
            icon_path: Optional path to the project logo icon
            config: Optional Config object for settings persistence
        """
        super().__init__()
        self.icon_path = icon_path
        self._config = config  # Store config reference directly
        self.slowest_keys_count = 10
        self._clipboard = QApplication.clipboard()
        self._trend_data_loaded = False
        self._typing_time_data_loaded = False
        self._histogram_data_loaded = False
        self._digraph_data_loaded = False
        self._trend_data_callback = None
        self._typing_time_data_callback = None
        self._histogram_data_callback = None
        # Unified controls state
        self._current_mode = "hardest"  # Default mode
        self._word_count = 10  # Default word count
        # Store all_time_best and trend for display
        self._all_time_best: float | None = None
        self._trend_wpm_per_day: float | None = None
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

    @staticmethod
    def _create_keycap_a_icon() -> QIcon:
        """Create a stylized 'A' keycap icon.

        Draws a keyboard key cap with the letter 'A' inside,
        using the application's palette colors for theme adaptation.

        Returns:
            QIcon with a keycap 'A' design
        """
        palette = QApplication.palette()
        text_color = palette.color(QPalette.Text)
        window_color = palette.color(QPalette.Window)

        icon = QIcon()
        sizes = [16, 22, 24, 32]

        for size in sizes:
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.transparent)

            from PySide6.QtGui import QFontMetricsF, QPainter, QPen

            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)

            # Key cap dimensions
            margin = 1
            key_width = size - 2 * margin
            key_height = size - 2 * margin
            corner_radius = size * 0.15

            # Draw key cap background (slightly lighter than window)
            bg_color = window_color.lighter(110)
            painter.setBrush(bg_color)
            painter.setPen(QPen(text_color, 1))

            # Draw rounded rectangle for key cap
            from PySide6.QtCore import QRectF

            key_rect = QRectF(margin, margin, key_width, key_height)
            painter.drawRoundedRect(key_rect, corner_radius, corner_radius)

            # Draw letter 'A' centered
            font = painter.font()
            font.setPixelSize(int(size * 0.5))
            font.setBold(True)
            painter.setFont(font)

            fm = QFontMetricsF(font)
            text = "A"
            text_width = fm.horizontalAdvance(text)
            text_height = fm.height()
            x = (size - text_width) / 2
            y = (size + text_height) / 2 - fm.descent()

            painter.setPen(text_color)
            painter.drawText(int(x), int(y), text)

            painter.end()

            # Add to icon with proper modes
            icon.addPixmap(pixmap, QIcon.Normal, QIcon.On)
            icon.addPixmap(pixmap, QIcon.Active, QIcon.On)
            icon.addPixmap(pixmap, QIcon.Selected, QIcon.On)

        return icon

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
        keystrokes_bursts_card = self._create_metric_card("Keystrokes & Bursts", "#3498db")
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
        tab_widget.addTab(overview_tab, self._create_palette_aware_icon("view-refresh"), "Overview")

        # Tab 2: Keys
        keys_tab = QWidget()
        keys_layout = QHBoxLayout(keys_tab)

        # Fastest Letter Keys (Left)
        fastest_keys_widget = QWidget()
        fastest_keys_layout = QVBoxLayout(fastest_keys_widget)
        self.fastest_title = QLabel(f"⚡ Fastest Letter Keys (Top {self.slowest_keys_count})")
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
        self.slowest_title = QLabel(f"🐌 Slowest Letter Keys (Top {self.slowest_keys_count})")
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

        tab_widget.addTab(keys_tab, self._create_keycap_a_icon(), "Keys")

        # Tab 3: Words
        words_tab = QWidget()
        words_layout = QVBoxLayout(words_tab)

        # Top section: Tables side by side
        tables_layout = QHBoxLayout()

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
        self.fastest_words_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.fastest_words_table.setRowCount(10)
        for i in range(10):
            self.fastest_words_table.setItem(i, 0, QTableWidgetItem("--"))
            self.fastest_words_table.setItem(i, 1, QTableWidgetItem("--"))
            self.fastest_words_table.setItem(i, 2, QTableWidgetItem("--"))
        fastest_words_layout.addWidget(self.fastest_words_table)

        tables_layout.addWidget(fastest_words_widget)

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
        self.hardest_words_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.hardest_words_table.setRowCount(10)
        for i in range(10):
            self.hardest_words_table.setItem(i, 0, QTableWidgetItem("--"))
            self.hardest_words_table.setItem(i, 1, QTableWidgetItem("--"))
            self.hardest_words_table.setItem(i, 2, QTableWidgetItem("--"))
        hardest_words_layout.addWidget(self.hardest_words_table)

        tables_layout.addWidget(hardest_words_widget)

        words_layout.addLayout(tables_layout)

        # Unified controls section (below both tables)
        unified_controls_layout = QHBoxLayout()

        # Mode dropdown
        mode_label = QLabel("Mode:")
        mode_label.setStyleSheet("font-size: 12px; color: #666;")
        unified_controls_layout.addWidget(mode_label)

        self.word_mode_combo = QComboBox()
        self.word_mode_combo.addItem("Hardest", "hardest")
        self.word_mode_combo.addItem("Fastest", "fastest")
        self.word_mode_combo.addItem("Mixed", "mixed")
        self.word_mode_combo.setCurrentIndex(0)  # Default to Hardest
        self.word_mode_combo.setMaximumWidth(100)
        unified_controls_layout.addWidget(self.word_mode_combo)

        # Count dropdown
        count_label = QLabel("Count:")
        count_label.setStyleSheet("font-size: 12px; color: #666;")
        unified_controls_layout.addWidget(count_label)

        self.unified_word_count_combo = QComboBox()
        self.unified_word_count_combo.addItem("10", 10)
        self.unified_word_count_combo.addItem("25", 25)
        self.unified_word_count_combo.addItem("50", 50)
        self.unified_word_count_combo.addItem("75", 75)
        self.unified_word_count_combo.addItem("100", 100)
        self.unified_word_count_combo.addItem("500", 500)
        self.unified_word_count_combo.addItem("1000", 1000)
        self.unified_word_count_combo.setCurrentIndex(0)  # Default to 10
        self.unified_word_count_combo.setMaximumWidth(80)
        unified_controls_layout.addWidget(self.unified_word_count_combo)

        # Action buttons
        self.unified_copy_btn = QPushButton("📋 Copy")
        self.unified_copy_btn.setStyleSheet("QPushButton { padding: 4px 12px; }")
        self.unified_copy_btn.clicked.connect(self.copy_words_by_mode)
        unified_controls_layout.addWidget(self.unified_copy_btn)

        self.unified_practice_btn = QPushButton("🐵 Practice (Monkeytype)")
        self.unified_practice_btn.setStyleSheet("QPushButton { padding: 4px 12px; }")
        self.unified_practice_btn.clicked.connect(self.practice_text_by_mode)
        self.unified_practice_btn.setToolTip(
            "Open Monkeytype with custom text for typing practice"
        )
        unified_controls_layout.addWidget(self.unified_practice_btn)

        self.unified_generate_btn = QPushButton("✨ Generate Text")
        self.unified_generate_btn.setStyleSheet("QPushButton { padding: 4px 12px; }")
        self.unified_generate_btn.setVisible(False)  # Hidden until Ollama detected
        self.unified_generate_btn.setToolTip("Generate practice text using Ollama")
        self.unified_generate_btn.clicked.connect(self.generate_text_by_mode)
        self._original_button_text = "✨ Generate Text"  # Store original text for restoration
        unified_controls_layout.addWidget(self.unified_generate_btn)

        # Special Characters checkbox
        self.words_special_chars_checkbox = QCheckBox("Special Chars")
        self.words_special_chars_checkbox.setToolTip(
            "Add special characters (quotes, hyphens, punctuation) to practice text (configurable probability in settings)"
        )
        self.words_special_chars_checkbox.setChecked(False)
        unified_controls_layout.addWidget(self.words_special_chars_checkbox)

        # Numbers checkbox
        self.words_numbers_checkbox = QCheckBox("Numbers")
        self.words_numbers_checkbox.setToolTip(
            "Add random numbers (1-1000) to practice text (configurable probability in settings)"
        )
        self.words_numbers_checkbox.setChecked(False)
        unified_controls_layout.addWidget(self.words_numbers_checkbox)

        unified_controls_layout.addStretch()
        words_layout.addLayout(unified_controls_layout)

        tab_widget.addTab(words_tab, self._create_palette_aware_icon("text-x-generic"), "Words")

        # Tab 4: Digraphs
        digraphs_tab = QWidget()
        digraphs_layout = QVBoxLayout(digraphs_tab)

        # Tables section (side by side)
        tables_layout = QHBoxLayout()

        # Fastest Digraphs (Left)
        fastest_digraphs_widget = QWidget()
        fastest_digraphs_layout = QVBoxLayout(fastest_digraphs_widget)
        self.fastest_digraphs_title = QLabel(f"⚡ Fastest Digraphs (Top {self.slowest_keys_count})")
        self.fastest_digraphs_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        fastest_digraphs_layout.addWidget(self.fastest_digraphs_title)

        self.fastest_digraphs_table = QTableWidget()
        self.fastest_digraphs_table.setFont(font)
        self.fastest_digraphs_table.setColumnCount(3)
        self.fastest_digraphs_table.setHorizontalHeaderLabels(["Digraph", "WPM", "Rank"])
        self.fastest_digraphs_table.verticalHeader().setVisible(False)
        self.fastest_digraphs_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.fastest_digraphs_table.setRowCount(self.slowest_keys_count)
        for i in range(self.slowest_keys_count):
            self.fastest_digraphs_table.setItem(i, 0, QTableWidgetItem("--"))
            self.fastest_digraphs_table.setItem(i, 1, QTableWidgetItem("--"))
            self.fastest_digraphs_table.setItem(i, 2, QTableWidgetItem("--"))
        fastest_digraphs_layout.addWidget(self.fastest_digraphs_table)

        tables_layout.addWidget(fastest_digraphs_widget)

        # Slowest Digraphs (Right)
        slowest_digraphs_widget = QWidget()
        slowest_digraphs_layout = QVBoxLayout(slowest_digraphs_widget)
        self.slowest_digraphs_title = QLabel(f"🐌 Slowest Digraphs (Top {self.slowest_keys_count})")
        self.slowest_digraphs_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        slowest_digraphs_layout.addWidget(self.slowest_digraphs_title)

        self.slowest_digraphs_table = QTableWidget()
        self.slowest_digraphs_table.setFont(font)
        self.slowest_digraphs_table.setColumnCount(3)
        self.slowest_digraphs_table.setHorizontalHeaderLabels(["Digraph", "WPM", "Rank"])
        self.slowest_digraphs_table.verticalHeader().setVisible(False)
        self.slowest_digraphs_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.slowest_digraphs_table.setRowCount(self.slowest_keys_count)
        for i in range(self.slowest_keys_count):
            self.slowest_digraphs_table.setItem(i, 0, QTableWidgetItem("--"))
            self.slowest_digraphs_table.setItem(i, 1, QTableWidgetItem("--"))
            self.slowest_digraphs_table.setItem(i, 2, QTableWidgetItem("--"))
        slowest_digraphs_layout.addWidget(self.slowest_digraphs_table)

        tables_layout.addWidget(slowest_digraphs_widget)

        digraphs_layout.addLayout(tables_layout)

        # Unified controls section (below both tables)
        digraph_controls_layout = QHBoxLayout()

        # Mode dropdown
        digraph_mode_label = QLabel("Mode:")
        digraph_mode_label.setStyleSheet("font-size: 12px; color: #666;")
        digraph_controls_layout.addWidget(digraph_mode_label)

        self.digraph_mode_combo = QComboBox()
        self.digraph_mode_combo.addItem("Hardest", "hardest")
        self.digraph_mode_combo.addItem("Fastest", "fastest")
        self.digraph_mode_combo.addItem("Mixed", "mixed")
        self.digraph_mode_combo.setCurrentIndex(0)  # Default to Hardest
        self.digraph_mode_combo.setMaximumWidth(100)
        digraph_controls_layout.addWidget(self.digraph_mode_combo)

        # Digraph count dropdown
        digraph_count_label = QLabel("Digraphs:")
        digraph_count_label.setStyleSheet("font-size: 12px; color: #666;")
        digraph_controls_layout.addWidget(digraph_count_label)

        self.digraph_count_combo = QComboBox()
        self.digraph_count_combo.addItem("5", 5)
        self.digraph_count_combo.addItem("10", 10)
        self.digraph_count_combo.addItem("20", 20)
        self.digraph_count_combo.addItem("50", 50)
        self.digraph_count_combo.setCurrentIndex(0)  # Default to 5
        self.digraph_count_combo.setMaximumWidth(80)
        digraph_controls_layout.addWidget(self.digraph_count_combo)

        # Word count dropdown
        digraph_word_count_label = QLabel("Words:")
        digraph_word_count_label.setStyleSheet("font-size: 12px; color: #666;")
        digraph_controls_layout.addWidget(digraph_word_count_label)

        self.digraph_word_count_combo = QComboBox()
        self.digraph_word_count_combo.addItem("10", 10)
        self.digraph_word_count_combo.addItem("25", 25)
        self.digraph_word_count_combo.addItem("50", 50)
        self.digraph_word_count_combo.addItem("75", 75)
        self.digraph_word_count_combo.addItem("100", 100)
        self.digraph_word_count_combo.addItem("200", 200)
        self.digraph_word_count_combo.addItem("500", 500)
        self.digraph_word_count_combo.addItem("1000", 1000)
        self.digraph_word_count_combo.setCurrentIndex(0)  # Default to 10
        self.digraph_word_count_combo.setMaximumWidth(80)
        digraph_controls_layout.addWidget(self.digraph_word_count_combo)

        # Action buttons
        self.digraph_copy_btn = QPushButton("📋 Copy")
        self.digraph_copy_btn.setStyleSheet("QPushButton { padding: 4px 12px; }")
        self.digraph_copy_btn.clicked.connect(self.copy_digraphs_by_mode)
        digraph_controls_layout.addWidget(self.digraph_copy_btn)

        self.digraph_practice_btn = QPushButton("🐵 Practice (Monkeytype)")
        self.digraph_practice_btn.setStyleSheet("QPushButton { padding: 4px 12px; }")
        self.digraph_practice_btn.setToolTip(
            "Open Monkeytype with words containing selected digraphs"
        )
        self.digraph_practice_btn.clicked.connect(self.practice_digraphs_by_mode)
        digraph_controls_layout.addWidget(self.digraph_practice_btn)

        # Special Characters checkbox
        self.digraphs_special_chars_checkbox = QCheckBox("Special Chars")
        self.digraphs_special_chars_checkbox.setToolTip(
            "Add special characters (quotes, hyphens, punctuation) to practice text (configurable probability in settings)"
        )
        self.digraphs_special_chars_checkbox.setChecked(False)
        digraph_controls_layout.addWidget(self.digraphs_special_chars_checkbox)

        # Numbers checkbox
        self.digraphs_numbers_checkbox = QCheckBox("Numbers")
        self.digraphs_numbers_checkbox.setToolTip(
            "Add random numbers (1-1000) to practice text (configurable probability in settings)"
        )
        self.digraphs_numbers_checkbox.setChecked(False)
        digraph_controls_layout.addWidget(self.digraphs_numbers_checkbox)

        digraph_controls_layout.addStretch()
        digraphs_layout.addLayout(digraph_controls_layout)

        tab_widget.addTab(
            digraphs_tab, self._create_palette_aware_icon("format-text-underline"), "Digraphs"
        )

        # Tab 5: Trends (NEW)
        trends_tab = QWidget()
        trends_layout = QVBoxLayout(trends_tab)

        from ui.wpm_graph import WPMTimeSeriesGraph

        self.wpm_graph = WPMTimeSeriesGraph()
        trends_layout.addWidget(self.wpm_graph)

        tab_widget.addTab(trends_tab, self._create_palette_aware_icon("go-up"), "Trends")

        # Tab 6: Typing Time
        typing_time_tab = QWidget()
        typing_time_layout = QVBoxLayout(typing_time_tab)

        from ui.typing_time_graph import TypingTimeGraph

        self.typing_time_graph = TypingTimeGraph()
        typing_time_layout.addWidget(self.typing_time_graph)

        tab_widget.addTab(
            typing_time_tab,
            self._create_palette_aware_icon("x-office-calendar"),
            "Timeline",
        )

        # Tab 7: Burst Speed Distribution
        histogram_tab = QWidget()
        histogram_layout = QVBoxLayout(histogram_tab)

        from ui.burst_histogram import BurstSpeedHistogram

        self.burst_histogram = BurstSpeedHistogram()
        histogram_layout.addWidget(self.burst_histogram)

        tab_widget.addTab(
            histogram_tab,
            self._create_palette_aware_icon("view-statistics"),
            "Bursts",
        )

        layout.addWidget(tab_widget)
        self.tab_widget = tab_widget
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        self.setLayout(layout)

        # Load checkbox states from config and connect signals
        config = self._get_config()
        if config:
            # Words tab checkboxes
            words_special_chars = config.get_bool("practice_words_special_chars_enabled", False)
            log.info(f"Loading practice_words_special_chars_enabled = {words_special_chars}")
            self.words_special_chars_checkbox.setChecked(words_special_chars)

            words_numbers = config.get_bool("practice_words_numbers_enabled", False)
            log.info(f"Loading practice_words_numbers_enabled = {words_numbers}")
            self.words_numbers_checkbox.setChecked(words_numbers)

            # Digraphs tab checkboxes
            digraphs_special_chars = config.get_bool("practice_digraphs_special_chars_enabled", False)
            log.info(f"Loading practice_digraphs_special_chars_enabled = {digraphs_special_chars}")
            self.digraphs_special_chars_checkbox.setChecked(digraphs_special_chars)
            digraphs_numbers = config.get_bool("practice_digraphs_numbers_enabled", False)
            log.info(f"Loading practice_digraphs_numbers_enabled = {digraphs_numbers}")
            self.digraphs_numbers_checkbox.setChecked(digraphs_numbers)

            # Load saved combo box values
            # Words mode
            saved_word_mode = config.get("practice_words_mode", "hardest")
            log.info(f"Loading saved_word_mode = {saved_word_mode}")
            for i in range(self.word_mode_combo.count()):
                if self.word_mode_combo.itemData(i) == saved_word_mode:
                    self.word_mode_combo.setCurrentIndex(i)
                    self._current_mode = saved_word_mode
                    break

            # Words count
            saved_word_count = config.get_int("practice_words_word_count", 10)
            log.info(f"Loading saved_word_count = {saved_word_count}")
            for i in range(self.unified_word_count_combo.count()):
                if self.unified_word_count_combo.itemData(i) == saved_word_count:
                    self.unified_word_count_combo.setCurrentIndex(i)
                    break

            # Digraphs mode
            saved_digraph_mode = config.get("practice_digraphs_mode", "hardest")
            log.info(f"Loading saved_digraph_mode = {saved_digraph_mode}")
            for i in range(self.digraph_mode_combo.count()):
                if self.digraph_mode_combo.itemData(i) == saved_digraph_mode:
                    self.digraph_mode_combo.setCurrentIndex(i)
                    break

            # Digraph count
            saved_digraph_count = config.get_int("practice_digraphs_digraph_count", 5)
            log.info(f"Loading saved_digraph_count = {saved_digraph_count}")
            for i in range(self.digraph_count_combo.count()):
                if self.digraph_count_combo.itemData(i) == saved_digraph_count:
                    self.digraph_count_combo.setCurrentIndex(i)
                    break

            # Digraph word count
            saved_digraph_word_count = config.get_int("practice_digraphs_word_count", 10)
            log.info(f"Loading saved_digraph_word_count = {saved_digraph_word_count}")
            for i in range(self.digraph_word_count_combo.count()):
                if self.digraph_word_count_combo.itemData(i) == saved_digraph_word_count:
                    self.digraph_word_count_combo.setCurrentIndex(i)
                    break

        # Connect Words tab checkbox signals
        self.words_special_chars_checkbox.stateChanged.connect(
            lambda s: self._update_practice_config("practice_words_special_chars_enabled", s)
        )
        self.words_numbers_checkbox.stateChanged.connect(
            lambda s: self._update_practice_config("practice_words_numbers_enabled", s)
        )

        # Connect Words tab combo box signals (after loading settings to avoid triggering during init)
        self.word_mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self.unified_word_count_combo.currentTextChanged.connect(
            lambda text: self._update_practice_config_int("practice_words_word_count", self.unified_word_count_combo.currentData())
        )

        # Connect Digraphs tab checkbox signals
        self.digraphs_special_chars_checkbox.stateChanged.connect(
            lambda s: self._update_practice_config("practice_digraphs_special_chars_enabled", s)
        )
        self.digraphs_numbers_checkbox.stateChanged.connect(
            lambda s: self._update_practice_config("practice_digraphs_numbers_enabled", s)
        )

        # Connect Digraphs tab combo box signals (after loading settings to avoid triggering during init)
        self.digraph_mode_combo.currentTextChanged.connect(
            lambda text: self._update_practice_config_str("practice_digraphs_mode", self.digraph_mode_combo.currentData())
        )
        self.digraph_count_combo.currentTextChanged.connect(
            lambda text: self._update_practice_config_int("practice_digraphs_digraph_count", self.digraph_count_combo.currentData())
        )
        self.digraph_word_count_combo.currentTextChanged.connect(
            lambda text: self._update_practice_config_int("practice_digraphs_word_count", self.digraph_word_count_combo.currentData())
        )

        # Set default window size (wider for better table display)
        self.resize(700, 500)

    def update_wpm(
        self,
        burst_wpm: float,
        today_best: float,
        long_term_avg: float,
        all_time_best: float,
        wpm_95th_percentile: float,
    ) -> None:
        """Update WPM display.

        Args:
            burst_wpm: Current burst WPM
            today_best: Personal best WPM today
            long_term_avg: Long-term average WPM
            all_time_best: All-time best WPM
            wpm_95th_percentile: 95th percentile WPM across all bursts
        """
        log.debug(f"update_wpm() called: burst_wpm={burst_wpm:.1f}, visible={self.isVisible()}")

        if not self.isVisible():
            log.debug("update_wpm() - panel not visible, returning early")
            return

        # Update Current Burst WPM card
        if hasattr(self, "burst_wpm_value_label"):
            self.burst_wpm_value_label.setText(f"{burst_wpm:.1f}")
            if today_best > 0:
                today_best_text = f"{today_best:.1f}"
            else:
                today_best_text = "--"
            if wpm_95th_percentile > 0:
                percentile_text = f"{wpm_95th_percentile:.1f}"
            else:
                percentile_text = "--"
            self.burst_wpm_subtitle_label.setText(
                f"today's best: {today_best_text} • 95% quantile: {percentile_text}"
            )

        # Update Long-term Average WPM card
        if hasattr(self, "avg_wpm_value_label"):
            if long_term_avg is not None and long_term_avg > 0:
                self.avg_wpm_value_label.setText(f"{long_term_avg:.1f}")
            else:
                self.avg_wpm_value_label.setText("--")

            # Store all_time_best for trend display
            self._all_time_best = all_time_best

            # Build subtitle with trend if available
            if all_time_best is not None and all_time_best > 0:
                base_text = f"all-time best: {all_time_best:.1f}"
            else:
                base_text = "all-time best: --"

            # Add trend if available
            if hasattr(self, "_trend_wpm_per_day") and self._trend_wpm_per_day is not None:
                subtitle = f"{base_text} • trend: {self._trend_wpm_per_day:+.2f} WPM/day"
                self.avg_wpm_subtitle_label.setText(subtitle)
                log.debug(f"update_wpm() set subtitle with trend: {subtitle}")
            else:
                self.avg_wpm_subtitle_label.setText(base_text)
                log.debug(f"update_wpm() set subtitle without trend (hasattr={hasattr(self, '_trend_wpm_per_day')}): {base_text}")

    def update_slowest_keys(self, slowest_keys: list[KeyPerformance]) -> None:
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

    def update_fastest_keys(self, fastest_keys: list[KeyPerformance]) -> None:
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

    def update_keystrokes_bursts(self, keystrokes: int, bursts: int, today_keystrokes: int) -> None:
        """Update all-time keystrokes and bursts display.

        Args:
            keystrokes: All-time total keystrokes
            bursts: All-time total bursts
            today_keystrokes: Today's keystrokes count
        """
        if not self.isVisible():
            return

        if hasattr(self, "keystrokes_bursts_value_label"):
            self.keystrokes_bursts_value_label.setText(self._format_large_number(keystrokes))
            self.keystrokes_bursts_subtitle_label.setText(
                f"{self._format_large_number(bursts)} bursts • today: {self._format_large_number(today_keystrokes)}"
            )

    def update_avg_burst_duration(
        self,
        avg_ms: int,
        min_ms: int,
        max_ms: int,
        percentile_95_ms: int,
        wpm_95th_percentile: float = 0,
    ) -> None:
        """Update average burst duration display.

        Args:
            avg_ms: Average burst duration in milliseconds
            min_ms: Minimum burst duration in milliseconds
            max_ms: Maximum burst duration in milliseconds
            percentile_95_ms: 95th percentile burst duration in milliseconds
            wpm_95th_percentile: 95th percentile burst WPM
        """
        if not self.isVisible():
            return

        if hasattr(self, "avg_burst_time_value_label"):
            if avg_ms >= 1000:
                self.avg_burst_time_value_label.setText(f"{avg_ms / 1000:.1f}s")
            else:
                self.avg_burst_time_value_label.setText(f"{avg_ms}ms")

            # Format min/max/95th percentile as subtitle, including 95th percentile WPM
            min_display = f"{min_ms / 1000:.1f}s" if min_ms >= 1000 else f"{min_ms}ms"
            max_display = f"{max_ms / 1000:.1f}s" if max_ms >= 1000 else f"{max_ms}ms"
            p95_display = (
                f"{percentile_95_ms / 1000:.1f}s"
                if percentile_95_ms >= 1000
                else f"{percentile_95_ms}ms"
            )
            wpm_95_display = f"{wpm_95th_percentile:.1f} WPM" if wpm_95th_percentile > 0 else "--"
            self.avg_burst_time_subtitle_label.setText(f"95%: {p95_display} • max: {max_display}")

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

    def update_hardest_words(self, words: list[WordStatisticsLite]) -> None:
        """Update hardest words display.

        Args:
            words: List of WordStatisticsLite models
        """
        if not self.isVisible():
            return

        for i, word_stat in enumerate(words):
            speed_ms_per_letter = word_stat.avg_speed_ms_per_letter
            projected_wpm = 12000 / speed_ms_per_letter if speed_ms_per_letter > 0 else 0
            self.hardest_words_table.setItem(i, 0, QTableWidgetItem(word_stat.word))
            self.hardest_words_table.setItem(i, 1, QTableWidgetItem(f"{projected_wpm:.1f}"))
            self.hardest_words_table.setItem(
                i,
                2,
                QTableWidgetItem(str(word_stat.rank) if word_stat.rank > 0 else "--"),
            )

        for i in range(len(words), 10):
            self.hardest_words_table.setItem(i, 0, QTableWidgetItem("--"))
            self.hardest_words_table.setItem(i, 1, QTableWidgetItem("--"))
            self.hardest_words_table.setItem(i, 2, QTableWidgetItem("--"))

    def update_fastest_words(self, words: list[WordStatisticsLite]) -> None:
        """Update fastest words display.

        Args:
            words: List of WordStatisticsLite models
        """
        if not self.isVisible():
            return

        for i, word_stat in enumerate(words):
            speed_ms_per_letter = word_stat.avg_speed_ms_per_letter
            projected_wpm = 12000 / speed_ms_per_letter if speed_ms_per_letter > 0 else 0
            self.fastest_words_table.setItem(i, 0, QTableWidgetItem(word_stat.word))
            self.fastest_words_table.setItem(i, 1, QTableWidgetItem(f"{projected_wpm:.1f}"))
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

    def update_trend_graph(self, data: tuple[list[float], list[int]]) -> None:
        """Update trend graph with new data.

        Args:
            data: Tuple of (raw_wpm_values, x_positions) - backend always returns raw data now
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

    def update_typing_time_graph(self, data: list[TypingTimeDataPoint]) -> None:
        """Update typing time graph with new data.

        Args:
            data: List of TypingTimeDataPoint models
        """
        log.debug(f"update_typing_time_graph() called with {len(data)} data points")
        slope = self.typing_time_graph.update_graph(data)
        log.debug(f"update_typing_time_graph() got slope: {slope}")
        self.update_trend_parameter(slope)

    def update_trend_parameter(self, wpm_per_day: float | None) -> None:
        """Update the trend parameter display in Overview tab.

        Args:
            wpm_per_day: WPM increase per day (positive or negative), or None if unavailable
        """
        log.debug(f"update_trend_parameter() called with wpm_per_day={wpm_per_day}")
        # Store the trend value
        self._trend_wpm_per_day = wpm_per_day

        if not hasattr(self, "avg_wpm_subtitle_label"):
            log.warning("avg_wpm_subtitle_label not found")
            return

        # Build subtitle with trend
        all_time_best = self._all_time_best
        if all_time_best is not None and all_time_best > 0:
            base_text = f"all-time best: {all_time_best:.1f}"
        else:
            base_text = "all-time best: --"

        if wpm_per_day is not None:
            subtitle = f"{base_text} • trend: {wpm_per_day:+.2f} WPM/day"
            self.avg_wpm_subtitle_label.setText(subtitle)
            log.debug(f"Set subtitle to: {subtitle}")
        else:
            subtitle = base_text
            self.avg_wpm_subtitle_label.setText(subtitle)
            log.debug(f"Set subtitle to (no trend): {subtitle}")

    def set_histogram_data_callback(self, callback) -> None:
        """Set callback for requesting histogram data.

        Args:
            callback: Function to call when new data is needed
        """
        self._histogram_data_callback = callback
        self.burst_histogram.set_data_callback(callback, load_immediately=False)

    def update_histogram_graph(self, data: list[tuple[float, int]]) -> None:
        """Update histogram graph with new data.

        Args:
            data: List of (bin_center_wpm, count) tuples
        """
        self.burst_histogram.update_graph(data)

    def update_recent_bursts(
        self, recent_bursts: list[tuple[int, float, int, int, int, int, str]]
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
        # Tab 3 is Digraphs (index 3)
        if index == 3 and not self._digraph_data_loaded:
            self._digraph_data_loaded = True
            # Trigger data load via callback
            if hasattr(self, "_digraph_data_callback") and self._digraph_data_callback is not None:
                self._digraph_data_callback()

        # Tab 4 is Trends (index 4)
        if index == 4 and not self._trend_data_loaded:
            self._trend_data_loaded = True
            # Trigger data load via callback
            if self._trend_data_callback is not None:
                self._trend_data_callback(self.wpm_graph.current_smoothness)

        # Tab 5 is Typing Time (index 5)
        if index == 5 and not self._typing_time_data_loaded:
            self._typing_time_data_loaded = True
            # Trigger data load via callback
            if self._typing_time_data_callback is not None:
                self._typing_time_data_callback(self.typing_time_graph.current_granularity.value)

        # Tab 6 is Burst Speed Distribution (index 6)
        if index == 6 and not self._histogram_data_loaded:
            self._histogram_data_loaded = True
            if self._histogram_data_callback is not None:
                self._histogram_data_callback(self.burst_histogram.bin_count)

    def copy_hardest_words_to_clipboard(self) -> None:
        """Copy the n slowest words to clipboard."""
        count = self.hardest_words_count_combo.currentData()
        if hasattr(self, "_request_words_for_clipboard_callback"):
            self._request_words_for_clipboard_callback(count, hardest=True)

    def copy_words_to_clipboard(self, words) -> None:
        """Copy words to clipboard.

        Args:
            words: List of WordStatisticsLite models or list of strings (enhanced words)
        """
        if words:
            # Handle both WordStatisticsLite objects and plain strings
            if words and hasattr(words[0], 'word'):
                word_list = [w.word for w in words]
            else:
                word_list = words
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

    def copy_fastest_words_to_clipboard(self) -> None:
        """Copy the n fastest words to clipboard."""
        count = self.fastest_words_count_combo.currentData()
        if hasattr(self, "_request_fastest_words_callback"):
            self._request_fastest_words_callback(count)

    def copy_mixed_words_to_clipboard(self) -> None:
        """Copy mixed random words (50% fastest, 50% hardest) to clipboard."""
        count = self.hardest_words_count_combo.currentData()
        if hasattr(self, "_request_mixed_words_callback"):
            self._request_mixed_words_callback(count)

    def practice_text(self) -> None:
        """Open clipboard text for typing practice."""
        from PySide6.QtGui import QClipboard

        # Get text from clipboard
        clipboard_text = self._clipboard.text(QClipboard.Mode.Clipboard)

        if not clipboard_text or not clipboard_text.strip():
            # Show error if clipboard is empty
            app = QApplication.instance()
            if app and hasattr(app, "tray_icon"):
                app.tray_icon.show_notification(
                    "Practice Error", "Clipboard is empty. Copy some text first."
                )
            return

        # Import directly and open Monkeytype
        try:
            from utils.monkeytype_url import generate_custom_text_url

            # Truncate text if too long
            words = clipboard_text.split()[:100]  # Limit to 100 words
            text_to_practice = " ".join(words)

            log.info(f"Opening typing practice: {len(words)} words")
            url = generate_custom_text_url(text_to_practice)
            webbrowser.open(url)

            log.info("Successfully opened typing practice")
            app = QApplication.instance()
            if app and hasattr(app, "tray_icon"):
                app.tray_icon.show_notification(
                    "Typing Practice", f"Opened with {len(words)} words from clipboard"
                )
        except Exception as e:
            log.error(f"Error opening practice: {e}")
            app = QApplication.instance()
            if app and hasattr(app, "tray_icon"):
                app.tray_icon.show_notification("Practice Error", f"Failed to open practice: {e}")

    def set_words_clipboard_callback(self, callback) -> None:
        """Set callback for fetching words for clipboard.

        Args:
            callback: Function to call with (count) parameter
        """
        self._request_words_for_clipboard_callback = callback

    def set_digraph_data_callback(self, callback) -> None:
        """Set callback for requesting digraph data.

        Args:
            callback: Function to call when new data is needed
        """
        self._digraph_data_callback = callback

    def set_fastest_words_clipboard_callback(self, callback) -> None:
        """Set callback for fetching fastest words for clipboard.

        Args:
            callback: Function to call with (count) parameter
        """
        self._request_fastest_words_callback = callback

    def set_mixed_words_clipboard_callback(self, callback) -> None:
        """Set callback for fetching mixed words for clipboard.

        Args:
            callback: Function to call with (count) parameter
        """
        self._request_mixed_words_callback = callback

    def set_text_generation_callback(self, callback) -> None:
        """Set callback for Ollama text generation.

        Args:
            callback: Function to call with (count) parameter
        """
        self._request_text_generation_callback = callback

    def set_ollama_available(self, available: bool) -> None:
        """Show/hide generate button based on Ollama availability.

        Args:
            available: True if Ollama server is running
        """
        # Use unified button if it exists, otherwise fall back to old button
        if hasattr(self, "unified_generate_btn"):
            self.unified_generate_btn.setVisible(available)
        elif hasattr(self, "generate_text_btn"):
            self.generate_text_btn.setVisible(available)

    def generate_text_with_ollama(self) -> None:
        """Generate text using Ollama with configured word count from settings."""
        log.info("Generate text button clicked")

        # Get word count from application config (LLM settings), not from combo box
        # Combo box is for "Copy Words" feature, generation uses configured word count
        app = QApplication.instance()
        if app and hasattr(app, "config"):
            count = self._get_config().get_int("llm_word_count", 50)
        else:
            count = 50  # Fallback default

        log.info(f"Requesting {count} words for generation (from LLM settings)")

        if hasattr(self, "_request_text_generation_callback"):
            # Update button to show generation in progress
            self.generate_text_btn.setEnabled(False)
            self.generate_text_btn.setText("⏳ Generating...")
            log.info(f"Calling text generation callback with count={count}")
            self._request_text_generation_callback(count)
        else:
            log.error("_request_text_generation_callback not set - cannot generate text")
            # Show error immediately
            self.on_text_generation_failed(
                "Text generation callback not initialized. Please restart the application."
            )

    def on_text_generated(self, text: str) -> None:
        """Handle generated text - copy to clipboard.

        Args:
            text: Generated text from Ollama
        """
        from PySide6.QtCore import QTimer
        from PySide6.QtGui import QClipboard

        # Copy to clipboard (both selection and clipboard)
        self._clipboard.setText(text, QClipboard.Mode.Selection)
        self._clipboard.setText(text, QClipboard.Mode.Clipboard)

        # Restore button state (use unified button if it exists, otherwise fall back to old)
        if hasattr(self, "unified_generate_btn"):
            btn = self.unified_generate_btn
        else:
            btn = self.generate_text_btn
        btn.setEnabled(True)
        word_count = len(text.split())
        btn.setText(f"✓ {word_count} words copied!")

        # Reset button text after 2 seconds
        QTimer.singleShot(2000, lambda: btn.setText(self._original_button_text))

        # Show notification
        app = QApplication.instance()
        if app and hasattr(app, "tray_icon"):
            app.tray_icon.show_notification(
                "Text Generated", f"Copied {word_count} words to clipboard"
            )

    def on_text_generation_failed(self, error: str) -> None:
        """Handle generation failure.

        Args:
            error: Error message
        """
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import (
            QDialog,
            QLabel,
            QPushButton,
            QTextEdit,
            QVBoxLayout,
        )

        # Log the error
        log.error(f"Text generation failed: {error}")

        # Restore button state
        self.generate_text_btn.setEnabled(True)
        self.generate_text_btn.setText("✗ Failed")

        # Reset button text after 3 seconds
        QTimer.singleShot(3000, lambda: self.generate_text_btn.setText(self._original_button_text))

        # Show error dialog with copy button
        dialog = QDialog(self)
        dialog.setWindowTitle("Text Generation Failed")
        dialog.setMinimumWidth(500)

        layout = QVBoxLayout()
        dialog.setLayout(layout)

        # Error message
        error_label = QLabel("<b>Failed to generate practice text</b>")
        error_label.setWordWrap(True)
        layout.addWidget(error_label)

        # Error details (in a text box for copying)
        error_text = QTextEdit()
        error_text.setPlainText(str(error))
        error_text.setReadOnly(True)
        error_text.setMaximumHeight(150)
        layout.addWidget(error_text)

        # Copy button
        copy_btn = QPushButton("📋 Copy Error to Clipboard")
        copy_btn.clicked.connect(lambda: self._copy_error_to_clipboard(str(error), dialog))
        layout.addWidget(copy_btn)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)

        dialog.exec()

        # Also show tray notification if available
        app = QApplication.instance()
        if app and hasattr(app, "tray_icon"):
            app.tray_icon.show_notification("Generation Failed", f"Error: {error}")

    def _copy_error_to_clipboard(self, error_text: str, dialog: QDialog) -> None:
        """Copy error text to clipboard.

        Args:
            error_text: Error message to copy
            dialog: Dialog to close after copying
        """

        clipboard = QApplication.clipboard()
        clipboard.setText(error_text)

        # Show brief confirmation
        close_btn = dialog.findChild(QPushButton, "Close")
        if close_btn:
            original_text = close_btn.text()
            close_btn.setText("✓ Copied!")
            from PySide6.QtCore import QTimer

            QTimer.singleShot(1000, lambda: close_btn.setText(original_text))

    def update_digraph_stats(
        self, fastest: list[DigraphPerformance], slowest: list[DigraphPerformance]
    ) -> None:
        """Update digraph statistics display.

        Args:
            fastest: List of fastest digraphs
            slowest: List of slowest digraphs
        """
        if not self.isVisible():
            return

        # Update fastest digraphs table
        for i, digraph in enumerate(fastest):
            digraph_str = f"{digraph.first_key}{digraph.second_key}"
            self.fastest_digraphs_table.setItem(i, 0, QTableWidgetItem(digraph_str))
            self.fastest_digraphs_table.setItem(i, 1, QTableWidgetItem(f"{digraph.wpm:.1f}"))
            self.fastest_digraphs_table.setItem(
                i,
                2,
                QTableWidgetItem(str(digraph.rank) if digraph.rank > 0 else "--"),
            )

        for i in range(len(fastest), self.slowest_keys_count):
            self.fastest_digraphs_table.setItem(i, 0, QTableWidgetItem("--"))
            self.fastest_digraphs_table.setItem(i, 1, QTableWidgetItem("--"))
            self.fastest_digraphs_table.setItem(i, 2, QTableWidgetItem("--"))

        # Update slowest digraphs table
        for i, digraph in enumerate(slowest):
            digraph_str = f"{digraph.first_key}{digraph.second_key}"
            self.slowest_digraphs_table.setItem(i, 0, QTableWidgetItem(digraph_str))
            self.slowest_digraphs_table.setItem(i, 1, QTableWidgetItem(f"{digraph.wpm:.1f}"))
            self.slowest_digraphs_table.setItem(
                i,
                2,
                QTableWidgetItem(str(digraph.rank) if digraph.rank > 0 else "--"),
            )

        for i in range(len(slowest), self.slowest_keys_count):
            self.slowest_digraphs_table.setItem(i, 0, QTableWidgetItem("--"))
            self.slowest_digraphs_table.setItem(i, 1, QTableWidgetItem("--"))
            self.slowest_digraphs_table.setItem(i, 2, QTableWidgetItem("--"))

    def showEvent(self, event) -> None:
        """Override to emit visibility signal when shown."""
        super().showEvent(event)
        self.visibility_changed.emit(True)

    def hideEvent(self, event) -> None:
        """Override to emit visibility signal when hidden."""
        super().hideEvent(event)
        self.visibility_changed.emit(False)

    # Unified controls methods

    def _on_mode_changed(self, index: int) -> None:
        """Handle mode dropdown change.

        Args:
            index: Index of the selected item
        """
        mode = self.word_mode_combo.currentData()
        self._current_mode = mode
        # Persist the mode setting
        self._update_practice_config_str("practice_words_mode", mode)

    def copy_words_by_mode(self) -> None:
        """Copy words based on selected mode."""
        count = self.unified_word_count_combo.currentData()
        mode = self.word_mode_combo.currentData()
        special_chars = self.words_special_chars_checkbox.isChecked()
        numbers = self.words_numbers_checkbox.isChecked()

        if hasattr(self, "_request_words_by_mode_callback"):
            self._request_words_by_mode_callback(mode, count, special_chars, numbers)

    def practice_text_by_mode(self) -> None:
        """Open clipboard text for typing practice with word highlighting."""
        from PySide6.QtGui import QClipboard

        # Get text from clipboard
        clipboard_text = self._clipboard.text(QClipboard.Mode.Clipboard)

        count = self.unified_word_count_combo.currentData()
        mode = self.word_mode_combo.currentData()

        # Get checkbox states
        special_chars = self.words_special_chars_checkbox.isChecked()
        numbers = self.words_numbers_checkbox.isChecked()

        if not clipboard_text or not clipboard_text.strip():
            # Auto-fetch words based on mode if clipboard is empty
            if hasattr(self, "_request_word_highlight_list_callback"):
                self._request_word_highlight_list_callback(
                    mode, count, None, special_chars, numbers
                )
            return

        # If clipboard has text, fetch word list for highlighting
        if hasattr(self, "_request_word_highlight_list_callback"):
            self._request_word_highlight_list_callback(
                mode, count, clipboard_text, special_chars, numbers
            )

    def generate_text_by_mode(self) -> None:
        """Generate text using Ollama based on selected mode."""
        count = self.unified_word_count_combo.currentData()
        mode = self.word_mode_combo.currentData()

        if hasattr(self, "_request_text_generation_by_mode_callback"):
            # Disable button and show loading state
            self.unified_generate_btn.setEnabled(False)
            self.unified_generate_btn.setText("⏳ Generating...")
            self._request_text_generation_by_mode_callback(mode, count)
        else:
            log.error("_request_text_generation_by_mode_callback not set - cannot generate text")
            # Show error immediately
            self.on_text_generation_failed(
                "Text generation callback not initialized. Please restart the application."
            )

    def launch_practice_with_highlighting(self, text: str, highlight_words: dict) -> None:
        """Launch typing practice with word highlighting.

        Note: Monkeytype doesn't support word highlighting, so this just opens
        the text for practice without highlighting.

        Args:
            text: Text to practice
            highlight_words: Dict with 'hardest' and/or 'fastest' keys containing word lists
                (Not supported by Monkeytype, logged for reference)
        """
        try:
            from utils.monkeytype_url import generate_custom_text_url

            # Log highlight words (Monkeytype doesn't support them)
            if highlight_words.get("hardest"):
                log.debug(f"Hardest words (not highlighted in Monkeytype): {highlight_words['hardest'][:5]}...")
            if highlight_words.get("fastest"):
                log.debug(f"Fastest words (not highlighted in Monkeytype): {highlight_words['fastest'][:5]}...")

            log.info(f"Opening typing practice with mode {self._current_mode}")
            url = generate_custom_text_url(text)
            webbrowser.open(url)

            log.info("Successfully opened typing practice")
            app = QApplication.instance()
            if app and hasattr(app, "tray_icon"):
                app.tray_icon.show_notification("Typing Practice", "Opened Monkeytype with custom text")

        except Exception as e:
            log.error(f"Error opening practice: {e}")
            app = QApplication.instance()
            if app and hasattr(app, "tray_icon"):
                app.tray_icon.show_notification("Practice Error", f"Failed to open practice: {e}")

    def set_words_by_mode_clipboard_callback(self, callback) -> None:
        """Set callback for fetching words by mode for clipboard.

        Args:
            callback: Function to call with (mode, count, special_chars, numbers) parameters
        """
        self._request_words_by_mode_callback = callback

    def set_words_by_mode_practice_callback(self, callback) -> None:
        """Set callback for fetching word highlight list by mode for practice.

        Args:
            callback: Function to call with (mode, count, text, special_chars, numbers) parameters
        """
        self._request_word_highlight_list_callback = callback

    def set_text_generation_by_mode_callback(self, callback) -> None:
        """Set callback for Ollama text generation by mode.

        Args:
            callback: Function to call with (mode, count) parameters
        """
        self._request_text_generation_by_mode_callback = callback

    # Digraph controls methods

    def copy_digraphs_by_mode(self) -> None:
        """Copy words containing selected digraphs to clipboard."""
        digraph_count = self.digraph_count_combo.currentData()
        word_count = self.digraph_word_count_combo.currentData()
        mode = self.digraph_mode_combo.currentData()
        special_chars = self.digraphs_special_chars_checkbox.isChecked()
        numbers = self.digraphs_numbers_checkbox.isChecked()

        if hasattr(self, "_request_digraph_words_callback"):
            self._request_digraph_words_callback(mode, digraph_count, word_count, special_chars, numbers)

    def practice_digraphs_by_mode(self) -> None:
        """Launch practice with words containing selected digraphs."""
        from PySide6.QtGui import QClipboard

        # Get text from clipboard
        clipboard_text = self._clipboard.text(QClipboard.Mode.Clipboard)

        digraph_count = self.digraph_count_combo.currentData()
        word_count = self.digraph_word_count_combo.currentData()
        mode = self.digraph_mode_combo.currentData()

        # Get checkbox states
        special_chars = self.digraphs_special_chars_checkbox.isChecked()
        numbers = self.digraphs_numbers_checkbox.isChecked()

        if not clipboard_text or not clipboard_text.strip():
            # Auto-fetch words based on mode if clipboard is empty
            if hasattr(self, "_request_digraph_practice_callback"):
                self._request_digraph_practice_callback(
                    mode, digraph_count, word_count, None, special_chars, numbers
                )
            return

        # If clipboard has text, use it for practice with digraph-based highlighting
        if hasattr(self, "_request_digraph_practice_callback"):
            self._request_digraph_practice_callback(
                mode, digraph_count, word_count, clipboard_text, special_chars, numbers
            )

    def set_digraph_words_clipboard_callback(self, callback) -> None:
        """Set callback for fetching words containing digraphs for clipboard.

        Args:
            callback: Function to call with (mode, digraph_count, word_count, special_chars, numbers) parameters
        """
        self._request_digraph_words_callback = callback

    def set_digraph_practice_callback(self, callback) -> None:
        """Set callback for launching practice with digraph-based word highlighting.

        Args:
            callback: Function to call with (mode, digraph_count, word_count, text, special_chars, numbers) parameters
        """
        self._request_digraph_practice_callback = callback

    def launch_practice_with_digraph_highlighting(self, text: str, digraphs: list) -> None:
        """Launch typing practice with digraph-based word highlighting.

        Note: Monkeytype doesn't support digraph highlighting, so this just opens
        the text for practice without highlighting.

        Args:
            text: Text to practice
            digraphs: List of digraph strings (e.g., ['th', 'he', 'in'])
                (Not supported by Monkeytype, logged for reference)
        """
        try:
            from utils.monkeytype_url import generate_custom_text_url

            # Log digraphs (Monkeytype doesn't support them)
            log.info(f"Opening typing practice with digraphs: {digraphs} (not highlighted in Monkeytype)")

            url = generate_custom_text_url(text)
            webbrowser.open(url)

            log.info("Successfully opened typing practice")
            app = QApplication.instance()
            if app and hasattr(app, "tray_icon"):
                app.tray_icon.show_notification("Typing Practice", "Opened Monkeytype with custom text")

        except Exception as e:
            log.error(f"Error opening practice: {e}")
            app = QApplication.instance()
            if app and hasattr(app, "tray_icon"):
                app.tray_icon.show_notification("Practice Error", f"Failed to open practice: {e}")

    def set_digraph_controls_enabled(self, enabled: bool) -> None:
        """Enable or disable digraph controls based on dictionary availability.

        When no dictionaries are configured (accept_all_mode), the digraph
        practice controls should be hidden since there's no word list to
        search for matching digraphs.

        Args:
            enabled: True to show controls, False to hide them
        """
        if hasattr(self, "digraph_mode_combo"):
            self.digraph_mode_combo.setVisible(enabled)
            self.digraph_count_combo.setVisible(enabled)
            self.digraph_word_count_combo.setVisible(enabled)
            self.digraph_copy_btn.setVisible(enabled)
            self.digraph_practice_btn.setVisible(enabled)

            # Also hide the labels if we're hiding the controls
            # Find the labels by their text content
            if hasattr(self, "digraph_mode_combo"):
                parent = self.digraph_mode_combo.parent()
                if parent:
                    for child in parent.findChildren(QLabel):
                        if child.text() in ["Mode:", "Digraphs:", "Words:"]:
                            child.setVisible(enabled)

    def _get_config(self):
        """Get the config object, trying multiple sources."""
        if self._config:
            return self._config
        app = QApplication.instance()
        if app and hasattr(app, "application") and hasattr(app.application, "config"):
            return app.application.config
        return None

    def _update_practice_config(self, key: str, state: int) -> None:
        """Update practice config when checkbox state changes.

        Args:
            key: Config key to update
            state: Qt.CheckState value (0=unchecked, 2=checked)
        """
        from PySide6.QtCore import Qt

        config = self._get_config()
        if config:
            is_checked = state == Qt.CheckState.Checked.value
            log.info(f"Updating config {key} = {is_checked}")
            config.set(key, is_checked)
        else:
            log.warning(f"Cannot update config {key}: config not available")

    def _update_practice_config_int(self, key: str, value: int) -> None:
        """Update practice config with integer value.

        Args:
            key: Config key to update
            value: Integer value to set
        """
        config = self._get_config()
        if config:
            log.info(f"Updating config {key} = {value}")
            config.set(key, value)
        else:
            log.warning(f"Cannot update config {key}: config not available")

    def _update_practice_config_str(self, key: str, value: str) -> None:
        """Update practice config with string value.

        Args:
            key: Config key to update
            value: String value to set
        """
        config = self._get_config()
        if config:
            log.info(f"Updating config {key} = {value}")
            config.set(key, value)
        else:
            log.warning(f"Cannot update config {key}: config not available")
