"""WPM burst sequence graph widget for RealTypeCoach."""

from collections.abc import Callable

import pyqtgraph as pg
from pyqtgraph import GraphicsLayoutWidget
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget


def calculate_linear_regression_burst(wpm_values: list[float]) -> tuple[float | None, float | None, float | None]:
    """Calculate linear regression (y = mx + b) for WPM over burst sequence.

    Args:
        wpm_values: List of WPM values

    Returns:
        Tuple of (slope_wpm_per_burst, intercept, r_squared) or (None, None, None) if insufficient data
    """
    if len(wpm_values) < 2:
        return None, None, None

    # Use burst numbers as x-axis (1, 2, 3, ...)
    burst_numbers = list(range(1, len(wpm_values) + 1))

    # Calculate slope and intercept using least squares
    n = len(burst_numbers)
    sum_x = sum(burst_numbers)
    sum_y = sum(wpm_values)
    sum_xy = sum(x * y for x, y in zip(burst_numbers, wpm_values))
    sum_x2 = sum(x * x for x in burst_numbers)

    denominator = n * sum_x2 - sum_x * sum_x
    if denominator == 0:
        return None, None, None

    slope = (n * sum_xy - sum_x * sum_y) / denominator
    intercept = (sum_y - slope * sum_x) / n

    # Calculate R² for trend quality
    y_mean = sum_y / n
    ss_tot = sum((y - y_mean) ** 2 for y in wpm_values)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(burst_numbers, wpm_values))
    r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

    # Slope is WPM per burst
    return slope, intercept, r_squared


def smoothness_to_alpha(smoothness: int) -> float:
    """Convert smoothness slider value (0-100) to exponential smoothing alpha.

    Matches keybr.com formula: alpha = 1 / 10^(smoothness * 3)
    where smoothness is normalized to 0-1 range.

    Args:
        smoothness: Slider value (0-100)

    Returns:
        Alpha value for exponential smoothing
    """
    if smoothness <= 0:
        return 1.0  # No smoothing
    normalized = smoothness / 100.0  # Convert 0-100 to 0-1
    return 1.0 / (10.0 ** (normalized * 3))


def apply_exponential_smoothing_client(values: list[float], smoothness: int) -> list[float]:
    """Apply exponential smoothing client-side for instant response.

    Uses keybr.com algorithm: value = alpha * input + (1 - alpha) * previous

    Args:
        values: Raw WPM values
        smoothness: Smoothness level (0-100)
                    0 = no smoothing (alpha=1.0)
                    50 = moderate smoothing (alpha≈0.03)
                    100 = maximum smoothing (alpha=0.001)

    Returns:
        Smoothed WPM values
    """
    if not values or smoothness <= 0:
        return values[:]

    alpha = smoothness_to_alpha(smoothness)
    smoothed = []
    for i, value in enumerate(values):
        if i == 0:
            smoothed.append(value)
        else:
            smoothed.append(alpha * value + (1 - alpha) * smoothed[-1])
    return smoothed


class WPMTimeSeriesGraph(QWidget):
    """Interactive WPM burst sequence graph with aggregation control."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.raw_wpm: list[float] = []  # Cache raw WPM data for instant smoothing
        self.current_smoothness = 0  # Default to raw data (no smoothing)
        self._data_callback: Callable[[int], None] | None = None
        self.plot_item = None
        self.trend_plot_item = None  # Will hold the trend line plot item
        self.current_slope_per_burst: float | None = None  # Store current slope for display

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

        # Create trend line plot item (initially empty)
        self.trend_plot_item = self.plot.plot(
            pen=pg.mkPen(color=(255, 140, 0), width=2, style=Qt.PenStyle.DashLine)
        )

        layout.addWidget(self.plot_widget)

        # Aggregation slider
        slider_label = QLabel("Smoothing:")
        layout.addWidget(slider_label)

        slider_control_layout = QHBoxLayout()

        left_label = QLabel("Raw Data")
        left_label.setStyleSheet("font-size: 11px; color: palette(text);")

        self.resolution_slider = QSlider(Qt.Horizontal)
        self.resolution_slider.setRange(0, 100)
        self.resolution_slider.setValue(0)  # Default to raw data (no smoothing)
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
        """Handle resolution slider change with instant response."""
        self.current_smoothness = value

        # Apply smoothing instantly to cached raw data
        if self.raw_wpm:
            self._update_with_cached_data()
        else:
            # No cached data yet, request from backend
            if self._data_callback:
                self._data_callback(value)

    def _update_with_cached_data(self) -> None:
        """Update plot using cached raw data with current smoothing level."""
        if not self.raw_wpm:
            return

        # Apply smoothing client-side
        smoothed = apply_exponential_smoothing_client(self.raw_wpm, self.current_smoothness)
        x_positions = list(range(1, len(smoothed) + 1))

        if not smoothed:
            self.plot_item.setData([], [])
            self.trend_plot_item.setData([], [])
            self.info_label.setText("Showing: No data")
            self.current_slope_per_burst = None
            return

        # Calculate trend line from RAW data (not smoothed)
        slope_per_burst, intercept, r_squared = calculate_linear_regression_burst(self.raw_wpm)
        self.current_slope_per_burst = slope_per_burst

        if slope_per_burst is not None and len(self.raw_wpm) >= 2:
            # Generate trend line points (start and end of burst sequence)
            start_burst = 1
            end_burst = len(x_positions)

            # Calculate WPM at start and end using the regression equation
            # WPM = slope * burst_number + intercept
            start_wpm = slope_per_burst * start_burst + intercept
            end_wpm = slope_per_burst * end_burst + intercept

            x_trend = [start_burst, end_burst]
            y_trend = [start_wpm, end_wpm]

            self.trend_plot_item.setData(x_trend, y_trend)
        else:
            self.trend_plot_item.setData([], [])
            self.current_slope_per_burst = None

        # Auto-scale y-axis based on current smoothed data and trend line
        y_min = min(smoothed)
        y_max = max(smoothed)
        # Add some padding (10% on each side, minimum 1 WPM)
        padding = max(1.0, (y_max - y_min) * 0.1)
        y_range = (y_min - padding, y_max + padding)

        # Update plot data
        self.plot_item.setData(x_positions, smoothed)

        # Auto-scale y-axis for current smoothing level
        self.plot.setYRange(y_range[0], y_range[1], padding=0)

        # Update info label
        trend_info = ""
        if self.current_slope_per_burst is not None:
            trend_info = f" • Trend: {self.current_slope_per_burst:+.3f} WPM/burst"
        self.info_label.setText(f"Showing: {len(smoothed)} data points{trend_info}")

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
            data: Tuple of (raw_wpm_values, x_positions) - backend always returns raw data now
        """
        raw_wpm, x_positions = data

        # Cache raw data for instant smoothing
        self.raw_wpm = raw_wpm[:]

        # Apply current smoothing level and update display
        self._update_with_cached_data()
