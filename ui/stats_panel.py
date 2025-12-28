"""Statistics panel for RealTypeCoach."""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QLabel,
                             QHBoxLayout, QFrame)
from PyQt5.QtCore import Qt
from typing import List, Tuple


class StatsPanel(QWidget):
    """Real-time statistics display panel."""

    def __init__(self):
        """Initialize statistics panel."""
        super().__init__()
        self.init_ui()

    def init_ui(self) -> None:
        """Initialize user interface."""
        layout = QVBoxLayout()

        self.title_label = QLabel("⌨ RealTypeCoach Statistics")
        self.title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(self.title_label)

        self.add_separator(layout)

        self.wpm_label = QLabel("Current WPM: --")
        self.wpm_label.setStyleSheet("font-size: 24px; color: #3daee9; font-weight: bold;")
        layout.addWidget(self.wpm_label)

        self.add_separator(layout)

        self.burst_wpm_label = QLabel("Burst WPM: --")
        self.burst_wpm_label.setStyleSheet("font-size: 16px;")
        layout.addWidget(self.burst_wpm_label)

        self.personal_best_label = QLabel("Personal Best Today: --")
        self.personal_best_label.setStyleSheet("font-size: 16px; color: #ff6b6b;")
        layout.addWidget(self.personal_best_label)

        self.add_separator(layout)

        self.slowest_title = QLabel("🐌 Slowest Letter Keys (Top 10)")
        self.slowest_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(self.slowest_title)

        self.slowest_keys_layout = QVBoxLayout()
        self.slowest_key_labels: List[QLabel] = []
        for i in range(10):
            label = QLabel(f"{i+1}. --")
            label.setStyleSheet("font-family: monospace; font-size: 12px;")
            self.slowest_key_labels.append(label)
            self.slowest_keys_layout.addWidget(label)
        layout.addLayout(self.slowest_keys_layout)

        self.add_separator(layout)

        self.fastest_title = QLabel("⚡ Fastest Letter Keys (Top 10)")
        self.fastest_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(self.fastest_title)

        self.fastest_keys_layout = QVBoxLayout()
        self.fastest_key_labels: List[QLabel] = []
        for i in range(10):
            label = QLabel(f"{i+1}. --")
            label.setStyleSheet("font-family: monospace; font-size: 12px;")
            self.fastest_key_labels.append(label)
            self.fastest_keys_layout.addWidget(label)
        layout.addLayout(self.fastest_keys_layout)

        self.add_separator(layout)

        self.hardest_words_title = QLabel("🐢 Hardest Words (All Time)")
        self.hardest_words_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(self.hardest_words_title)

        self.hardest_words_layout = QVBoxLayout()
        self.hardest_word_labels: List[QLabel] = []
        for i in range(10):
            label = QLabel(f"{i+1}. --")
            label.setStyleSheet("font-family: monospace; font-size: 12px;")
            self.hardest_word_labels.append(label)
            self.hardest_words_layout.addWidget(label)
        layout.addLayout(self.hardest_words_layout)

        self.add_separator(layout)

        self.fastest_words_title = QLabel("⚡ Fastest Words (All Time)")
        self.fastest_words_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(self.fastest_words_title)

        self.fastest_words_layout = QVBoxLayout()
        self.fastest_word_labels: List[QLabel] = []
        for i in range(10):
            label = QLabel(f"{i+1}. --")
            label.setStyleSheet("font-family: monospace; font-size: 12px;")
            self.fastest_word_labels.append(label)
            self.fastest_words_layout.addWidget(label)
        layout.addLayout(self.fastest_words_layout)

        self.add_separator(layout)

        self.today_stats_label = QLabel("Today's Stats:")
        self.today_stats_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(self.today_stats_label)

        self.keystrokes_label = QLabel("Keystrokes: 0")
        self.keystrokes_label.setStyleSheet("font-size: 12px;")
        layout.addWidget(self.keystrokes_label)

        self.bursts_label = QLabel("Bursts: 0")
        self.bursts_label.setStyleSheet("font-size: 12px;")
        layout.addWidget(self.bursts_label)

        self.typing_time_label = QLabel("Typing time: 0m 0s")
        self.typing_time_label.setStyleSheet("font-size: 12px;")
        layout.addWidget(self.typing_time_label)

        layout.addStretch()
        self.setLayout(layout)

    def add_separator(self, layout: QVBoxLayout) -> None:
        """Add a separator line."""
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

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
            label = self.slowest_key_labels[i]
            label.setText(f"{i+1}. '{key_name}' - {avg_time:.1f}ms")

        for i in range(len(slowest_keys), len(self.slowest_key_labels)):
            self.slowest_key_labels[i].setText(f"{i+1}. --")

    def update_fastest_keys(self, fastest_keys: List[Tuple[int, str, float]]) -> None:
        """Update fastest keys display.

        Args:
            fastest_keys: List of (keycode, key_name, avg_time_ms) tuples
        """
        for i, (keycode, key_name, avg_time) in enumerate(fastest_keys):
            label = self.fastest_key_labels[i]
            label.setText(f"{i+1}. '{key_name}' - {avg_time:.1f}ms")

        for i in range(len(fastest_keys), len(self.fastest_key_labels)):
            self.fastest_key_labels[i].setText(f"{i+1}. --")

    def update_today_stats(self, keystrokes: int, bursts: int,
                         typing_sec: int) -> None:
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
            label = self.hardest_word_labels[i]
            label.setText(f"{i+1}. '{word}' - {speed_ms_per_letter:.1f} ms/letter ({duration_ms} ms, {num_letters} letters)")

        for i in range(len(words), len(self.hardest_word_labels)):
            self.hardest_word_labels[i].setText(f"{i+1}. --")

    def update_fastest_words(self, words: List[Tuple[str, float, int, int]]) -> None:
        """Update fastest words display.

        Args:
            words: List of (word, avg_speed_ms_per_letter, duration_ms, num_letters) tuples
        """
        for i, (word, speed_ms_per_letter, duration_ms, num_letters) in enumerate(words):
            label = self.fastest_word_labels[i]
            label.setText(f"{i+1}. '{word}' - {speed_ms_per_letter:.1f} ms/letter ({duration_ms} ms, {num_letters} letters)")

        for i in range(len(words), len(self.fastest_word_labels)):
            self.fastest_word_labels[i].setText(f"{i+1}. --")
