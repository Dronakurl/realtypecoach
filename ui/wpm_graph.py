"""WPM burst sequence graph widget for RealTypeCoach."""

import pyqtgraph as pg
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider
from PySide6.QtCore import Qt, QTimer
from pyqtgraph import GraphicsLayoutWidget
from typing import List, Callable, Optional


class WPMTimeSeriesGraph(QWidget):
    """Interactive WPM burst sequence graph with aggregation control."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data: List[float] = []
        self.current_window_size = 10  # Default 10-burst average
        self._data_callback: Optional[Callable[[int], None]] = None
        self._update_timer: Optional[QTimer] = None
        self.plot_item = None

        self.init_ui()

    def init_ui(self) -> None:
        """Initialize user interface."""
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)

        # Title
        title = QLabel("📈 WPM over Bursts")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        # PyQtGraph GraphicsLayoutWidget for plot
        self.plot_widget = GraphicsLayoutWidget()

        # Create plot
        self.plot = self.plot_widget.addPlot(row=0, col=0)
        self.plot.setLabel("left", "WPM")
        self.plot.setLabel("bottom", "Burst Number")
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.plot.showButtons()

        # Enable auto-range for both axes
        self.plot.enableAutoRange()

        # Create plot item with line and markers
        self.plot_item = self.plot.plot(
            pen=pg.mkPen(color=(50, 150, 200), width=2), symbol="o", symbolSize=5
        )

        layout.addWidget(self.plot_widget)

        # Aggregation slider
        slider_label = QLabel("Aggregation:")
        layout.addWidget(slider_label)

        slider_control_layout = QHBoxLayout()

        left_label = QLabel("Per Burst")
        left_label.setStyleSheet("font-size: 11px; color: palette(text);")

        self.resolution_slider = QSlider(Qt.Horizontal)
        self.resolution_slider.setRange(0, 100)
        self.resolution_slider.setValue(5)  # Default to ~10 burst average
        self.resolution_slider.valueChanged.connect(self.on_resolution_changed)

        right_label = QLabel("200-Burst Avg")
        right_label.setStyleSheet("font-size: 11px; color: palette(text);")

        slider_control_layout.addWidget(left_label)
        slider_control_layout.addWidget(self.resolution_slider, 1)
        slider_control_layout.addWidget(right_label)

        layout.addLayout(slider_control_layout)

        # Info label
        self.info_label = QLabel("Showing: No data")
        self.info_label.setStyleSheet("font-size: 11px; color: #888;")
        layout.addWidget(self.info_label)

        self.setLayout(layout)

    def on_resolution_changed(self, value: int) -> None:
        """Handle resolution slider change with debouncing."""
        if self._update_timer is not None:
            self._update_timer.stop()

        self._update_timer = QTimer()
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(lambda: self._update_resolution(value))
        self._update_timer.start(150)  # 150ms debounce

    def _update_resolution(self, value: int) -> None:
        """Update graph with new window size."""
        # Map slider value (0-100) to window size (1-200)
        window_size = max(1, int((value / 100) * 200))

        self.current_window_size = window_size

        # Request new data with this window size
        if self._data_callback:
            self._data_callback(window_size)

    def set_data_callback(self, callback: Callable[[int], None]) -> None:
        """Set callback for requesting new data."""
        self._data_callback = callback
        # Load initial data
        if self._data_callback:
            self._data_callback(self.current_window_size)

    def update_graph(self, wpm_values: List[float]) -> None:
        """Update graph with WPM values over burst sequence.

        Args:
            wpm_values: List of WPM values (one per data point)
        """
        self.data = wpm_values

        if not wpm_values:
            self.plot_item.setData([], [])
            self.info_label.setText("Showing: No data")
            return

        # Create x-axis as burst numbers
        burst_numbers = list(range(1, len(wpm_values) + 1))

        # Update plot data
        self.plot_item.setData(burst_numbers, wpm_values)

        # Enable auto-range with padding after data update
        self.plot.enableAutoRange(axis='xy', enable=True)

        # Update info label
        self.info_label.setText(f"Showing: {len(wpm_values)} data points")
