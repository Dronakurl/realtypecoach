"""WPM burst sequence graph widget for RealTypeCoach."""

from collections.abc import Callable

import pyqtgraph as pg
from pyqtgraph import GraphicsLayoutWidget
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget


class WPMTimeSeriesGraph(QWidget):
    """Interactive WPM burst sequence graph with aggregation control."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data: list[float] = []
        self.current_smoothness = 1  # Default to raw data
        self._data_callback: Callable[[int], None] | None = None
        self._update_timer: QTimer | None = None
        self.plot_item = None
        self._y_range: tuple[float, float] | None = None  # Store initial y-range

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

        left_label = QLabel("Raw Data")
        left_label.setStyleSheet("font-size: 11px; color: palette(text);")

        self.resolution_slider = QSlider(Qt.Horizontal)
        self.resolution_slider.setRange(1, 100)
        self.resolution_slider.setValue(1)  # Default to raw data
        self.resolution_slider.valueChanged.connect(self.on_resolution_changed)

        right_label = QLabel("Trend Line")
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
        self.current_smoothness = value

        # Request new data with this window size
        if self._data_callback:
            self._data_callback(value)

    def set_data_callback(
        self, callback: Callable[[int], None], load_immediately: bool = False
    ) -> None:
        """Set callback for requesting new data.

        Args:
            callback: Function to call with smoothness level (1-100)
            load_immediately: If True, load data immediately. If False, wait for explicit request.
        """
        self._data_callback = callback
        # Load initial data only if requested
        if load_immediately and self._data_callback:
            self._data_callback(self.current_smoothness)

    def update_graph(self, data: tuple[list[float], list[int]]) -> None:
        """Update graph with WPM values over burst sequence.

        Args:
            data: Tuple of (wpm_values, x_positions)
        """
        wpm_values, x_positions = data
        self.data = wpm_values

        if not wpm_values:
            self.plot_item.setData([], [])
            self.info_label.setText("Showing: No data")
            self._y_range = None
            return

        # Store y-range on first load
        if self._y_range is None:
            y_min = min(wpm_values)
            y_max = max(wpm_values)
            # Add some padding (10% on each side)
            padding = (y_max - y_min) * 0.1
            self._y_range = (y_min - padding, y_max + padding)

        # Update plot data with actual burst positions
        self.plot_item.setData(x_positions, wpm_values)

        # Maintain y-axis range for consistent visualization
        self.plot.setYRange(self._y_range[0], self._y_range[1], padding=0)

        # Update info label
        self.info_label.setText(f"Showing: {len(wpm_values)} data points")
