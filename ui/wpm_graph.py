"""WPM burst sequence graph widget for RealTypeCoach."""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider
from PySide6.QtCore import Qt, QTimer
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from typing import List, Callable, Optional

# Configure matplotlib to use standard font to avoid "Sans Not-Rotated" warning
import matplotlib

matplotlib.rcParams["font.family"] = "DejaVu Sans"
matplotlib.rcParams["font.sans-serif"] = [
    "DejaVu Sans",
    "Arial",
    "Liberation Sans",
    "sans-serif",
]


class WPMTimeSeriesGraph(QWidget):
    """Interactive WPM burst sequence graph with aggregation control."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data: List[float] = []
        self.current_window_size = 10  # Default 10-burst average
        self._data_callback: Optional[Callable[[int], None]] = None
        self._update_timer: Optional[QTimer] = None

        self.init_ui()

    def init_ui(self) -> None:
        """Initialize user interface."""
        layout = QVBoxLayout()

        # Title
        title = QLabel("📈 WPM over Bursts")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        # Matplotlib figure
        self.figure = Figure(figsize=(8, 4), dpi=100)
        self.canvas = FigureCanvasQTAgg(self.figure)
        layout.addWidget(self.canvas)

        # Navigation toolbar (zoom, pan, home)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        layout.addWidget(self.toolbar)

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
        self.figure.clear()

        if not wpm_values:
            ax = self.figure.add_subplot(111)
            ax.text(
                0.5,
                0.5,
                "No data available",
                ha="center",
                va="center",
                transform=ax.transAxes,
            )
            self.canvas.draw()
            self.info_label.setText("Showing: No data")
            return

        # Create x-axis as burst numbers
        burst_numbers = list(range(1, len(wpm_values) + 1))

        # Create plot
        ax = self.figure.add_subplot(111)
        ax.plot(
            burst_numbers,
            wpm_values,
            linewidth=2,
            color="#3daee9",
            marker="o",
            markersize=4 if len(wpm_values) < 100 else 2,
        )

        # Format axes
        ax.set_xlabel("Burst Number", fontsize=10)
        ax.set_ylabel("WPM", fontsize=10)
        ax.grid(True, alpha=0.3, linestyle="--")

        # Adjust layout with margins to prevent cutoff
        self.figure.subplots_adjust(
            left=0.12, right=0.95, top=0.92, bottom=0.15
        )

        # Redraw canvas
        self.canvas.draw()

        # Update info label
        self.info_label.setText(f"Showing: {len(wpm_values)} data points")
