"""Burst speed histogram widget for RealTypeCoach."""

from typing import List, Tuple, Callable, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)
from pyqtgraph import BarGraphItem, GraphicsLayoutWidget


class BurstSpeedHistogram(QWidget):
    """Histogram showing distribution of burst WPM values."""

    def __init__(self, parent: Optional[QWidget] = None):
        """Initialize burst speed histogram widget.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.bin_count = 50  # Default bin count
        self.data: List[Tuple[float, int]] = []
        self._data_callback: Optional[Callable[[int], None]] = None
        self._update_timer: Optional[QTimer] = None
        self.bar_item = None
        self.init_ui()

    def init_ui(self) -> None:
        """Initialize user interface."""
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)

        # Title
        title = QLabel("Burst Speed Distribution")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        # PyQtGraph plot widget
        self.plot_widget = GraphicsLayoutWidget()
        self.plot = self.plot_widget.addPlot(row=0, col=0)
        self.plot.setLabel("left", "Number of Bursts")
        self.plot.setLabel("bottom", "WPM")
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.plot.showButtons()
        self.plot.enableAutoRange()

        # Create bar chart item
        self.bar_item = BarGraphItem(x=[], height=[], width=0.8, brush=(150, 100, 200))
        self.plot.addItem(self.bar_item)

        layout.addWidget(self.plot_widget)

        # Controls row
        controls_layout = QGridLayout()

        # Bin count slider
        slider_label = QLabel("Bins:")
        controls_layout.addWidget(slider_label, 0, 0)

        left_label = QLabel("10")
        left_label.setStyleSheet("font-size: 11px;")

        self.bin_slider = QSlider(Qt.Horizontal)
        self.bin_slider.setRange(10, 200)
        self.bin_slider.setValue(50)
        self.bin_slider.valueChanged.connect(self.on_bin_count_changed)

        right_label = QLabel("200")
        right_label.setStyleSheet("font-size: 11px;")

        controls_layout.addWidget(left_label, 0, 1)
        controls_layout.addWidget(self.bin_slider, 0, 2)
        controls_layout.addWidget(right_label, 0, 3)

        # Refresh button
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.request_data)
        controls_layout.addWidget(refresh_btn, 0, 4)

        layout.addLayout(controls_layout)

        # Info label
        self.info_label = QLabel("Showing: No data")
        self.info_label.setStyleSheet("font-size: 11px; color: #888;")
        layout.addWidget(self.info_label)

        self.setLayout(layout)

    def on_bin_count_changed(self, value: int) -> None:
        """Handle bin count slider change with debouncing.

        Args:
            value: New slider value (bin count)
        """
        if self._update_timer is not None:
            self._update_timer.stop()

        self._update_timer = QTimer()
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(lambda: self._update_bin_count(value))
        self._update_timer.start(300)

    def _update_bin_count(self, value: int) -> None:
        """Update graph with new bin count.

        Args:
            value: New bin count
        """
        self.bin_count = value
        if self._data_callback:
            self._data_callback(self.bin_count)

    def set_data_callback(
        self, callback: Callable[[int], None], load_immediately: bool = False
    ) -> None:
        """Set callback for requesting new data.

        Args:
            callback: Function to call with bin count
            load_immediately: If True, load data immediately
        """
        self._data_callback = callback
        if load_immediately and self._data_callback:
            self._data_callback(self.bin_count)

    def request_data(self) -> None:
        """Request data update using callback."""
        if self._data_callback:
            self._data_callback(self.bin_count)

    def update_graph(self, histogram_data: List[Tuple[float, int]]) -> None:
        """Update histogram with new data.

        Args:
            histogram_data: List of (bin_center_wpm, count) tuples
        """
        self.data = histogram_data

        if not histogram_data:
            self.bar_item.setOpts(x=[], height=[])
            self.info_label.setText("Showing: No data")
            return

        # Extract x (bin centers) and y (counts)
        bin_centers = [item[0] for item in histogram_data]
        counts = [item[1] for item in histogram_data]

        # Update bar chart
        self.bar_item.setOpts(x=bin_centers, height=counts)

        # Calculate bar width dynamically
        if len(bin_centers) > 1:
            bar_width = (bin_centers[1] - bin_centers[0]) * 0.8
            self.bar_item.setOpts(width=bar_width)

        # Auto-scale axes
        self.plot.enableAutoRange(axis="xy", enable=True)

        # Update info label
        total_bursts = sum(counts)
        min_wpm = min(bin_centers) if bin_centers else 0
        max_wpm = max(bin_centers) if bin_centers else 0
        self.info_label.setText(
            f"Showing: {len(histogram_data)} bins across {total_bursts} bursts "
            f"(WPM range: {min_wpm:.0f} - {max_wpm:.0f})"
        )
