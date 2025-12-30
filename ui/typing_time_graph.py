"""Typing time graph widget for RealTypeCoach."""

from enum import Enum
from typing import List, Callable, Optional
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
)
from PySide6.QtCore import Qt, QTimer
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from core.models import TypingTimeDataPoint

# Configure matplotlib to use standard font
import matplotlib

matplotlib.rcParams["font.family"] = "DejaVu Sans"
matplotlib.rcParams["font.sans-serif"] = [
    "DejaVu Sans",
    "Arial",
    "Liberation Sans",
    "sans-serif",
]


class TimeGranularity(Enum):
    """Time period granularity options."""

    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    QUARTER = "quarter"


class TypingTimeGraph(QWidget):
    """Dual-plot stacked graph for typing time and WPM over time."""

    def __init__(self, parent: Optional[QWidget] = None):
        """Initialize typing time graph widget.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        # State
        self.current_granularity = TimeGranularity.DAY
        self.data: List[TypingTimeDataPoint] = []
        self._data_callback: Optional[Callable[[str], None]] = None
        self._update_timer: Optional[QTimer] = None

        self.init_ui()

    def init_ui(self) -> None:
        """Initialize user interface components."""
        # Main layout
        layout = QVBoxLayout()

        # Title section
        title = QLabel("Typing Time Over Time")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        # Controls row
        controls_layout = QHBoxLayout()

        # Granularity selector
        granularity_label = QLabel("Time Period:")
        controls_layout.addWidget(granularity_label)

        self.granularity_combo = QComboBox()
        self.granularity_combo.addItem("Day", TimeGranularity.DAY)
        self.granularity_combo.addItem("Week", TimeGranularity.WEEK)
        self.granularity_combo.addItem("Month", TimeGranularity.MONTH)
        self.granularity_combo.addItem("Quarter", TimeGranularity.QUARTER)
        self.granularity_combo.setCurrentIndex(0)  # Default to Day
        self.granularity_combo.currentIndexChanged.connect(
            self.on_granularity_changed
        )
        controls_layout.addWidget(self.granularity_combo)

        # Refresh button
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.request_data)
        controls_layout.addWidget(refresh_btn)

        controls_layout.addStretch()
        layout.addLayout(controls_layout)

        # Matplotlib figure with two subplots (vertically stacked)
        self.figure = Figure(figsize=(10, 8), dpi=100)

        # Create subplots with shared X-axis
        self.ax_time = self.figure.add_subplot(211)  # Top: Typing time
        self.ax_wpm = self.figure.add_subplot(
            212, sharex=self.ax_time
        )  # Bottom: WPM

        # Adjust subplot spacing to prevent label cutoff
        self.figure.subplots_adjust(
            hspace=0.15,  # Gap between plots
            left=0.15,  # More space for y-axis labels
            right=0.95,
            top=0.92,
            bottom=0.18,  # More space for x-axis labels
        )

        self.canvas = FigureCanvasQTAgg(self.figure)
        layout.addWidget(self.canvas)

        # Navigation toolbar
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        layout.addWidget(self.toolbar)

        # Info label
        self.info_label = QLabel("Showing: No data")
        self.info_label.setStyleSheet("font-size: 11px; color: #888;")
        layout.addWidget(self.info_label)

        self.setLayout(layout)

    def on_granularity_changed(self, index: int) -> None:
        """Handle granularity combo box change with debouncing.

        Args:
            index: Selected index in combo box
        """
        # Get selected granularity
        granularity = self.granularity_combo.itemData(index)

        if self._update_timer is not None:
            self._update_timer.stop()

        # Debounce to avoid excessive queries during rapid selection
        self._update_timer = QTimer()
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(lambda: self._update_granularity(granularity))
        self._update_timer.start(300)  # 300ms debounce

    def _update_granularity(self, granularity: TimeGranularity) -> None:
        """Update graph with new granularity.

        Args:
            granularity: New time granularity
        """
        self.current_granularity = granularity

        # Request new data
        self.request_data()

    def set_data_callback(self, callback: Callable[[str], None]) -> None:
        """Set callback for requesting new data.

        The callback will be called with granularity string ("day", "week", "month", "quarter")
        whenever new data is needed.

        Args:
            callback: Function to call with granularity string
        """
        self._data_callback = callback
        # Load initial data after event loop is running
        if self._data_callback:
            from PySide6.QtCore import QTimer
            # Use QTimer to schedule callback for next event loop iteration
            QTimer.singleShot(0, lambda: self._data_callback(self.current_granularity.value))

    def request_data(self) -> None:
        """Request data update using callback."""
        if self._data_callback:
            self._data_callback(self.current_granularity.value)

    def update_graph(self, data_points: List[TypingTimeDataPoint]) -> None:
        """Update both plots with typing time and WPM data.

        Args:
            data_points: List of TypingTimeDataPoint models
        """
        import logging
        import traceback
        log = logging.getLogger("realtypecoach.typing_time_graph")

        try:
            log.info(f"update_graph called with {len(data_points)} data points")

            self.data = data_points

            # Clear both subplots
            self.ax_time.clear()
            self.ax_wpm.clear()

            if not data_points:
                log.warning("No data points received, showing 'No data available'")
                # Show "No data" message on both plots
                for ax, title in [(self.ax_time, "Typing Time"), (self.ax_wpm, "WPM")]:
                    ax.text(
                        0.5,
                        0.5,
                        "No data available",
                        ha="center",
                        va="center",
                        transform=ax.transAxes,
                        fontsize=12,
                    )
                    ax.set_ylabel(title)

                self.canvas.draw()
                self.info_label.setText("Showing: No data")
                return

            # Extract data
            period_labels = [dp.period_label for dp in data_points]
            typing_hours = [
                dp.total_typing_ms / 3600000.0 for dp in data_points
            ]  # Convert to hours
            avg_wpm = [dp.avg_wpm for dp in data_points]

            # Plot 1: Typing Time (top)
            self.ax_time.plot(
                range(len(period_labels)),
                typing_hours,
                linewidth=2,
                color="#3daee9",
                marker="o",
                markersize=4 if len(data_points) < 50 else 2,
            )
            self.ax_time.set_ylabel("Typing Time (hours)", fontsize=10)
            self.ax_time.grid(True, alpha=0.3, linestyle="--")
            self.ax_time.tick_params(labelbottom=False)  # Hide X labels on top plot

            # Plot 2: Average WPM (bottom)
            self.ax_wpm.plot(
                range(len(period_labels)),
                avg_wpm,
                linewidth=2,
                color="#4caf50",
                marker="o",
                markersize=4 if len(data_points) < 50 else 2,
            )
            self.ax_wpm.set_ylabel("Average WPM", fontsize=10)
            self.ax_wpm.set_xlabel("Time Period", fontsize=10)
            self.ax_wpm.grid(True, alpha=0.3, linestyle="--")

            # Set X-axis labels (only on bottom plot)
            # Rotate labels if many data points
            if len(data_points) > 20:
                self.ax_wpm.set_xticks(
                    range(0, len(period_labels), max(1, len(period_labels) // 10))
                )
                self.ax_wpm.set_xticklabels(
                    [
                        period_labels[i]
                        for i in range(
                            0, len(period_labels), max(1, len(period_labels) // 10)
                        )
                    ],
                    rotation=45,
                    ha="right",
                    fontsize=8,
                )
            else:
                self.ax_wpm.set_xticks(range(len(period_labels)))
                self.ax_wpm.set_xticklabels(period_labels, rotation=45, ha="right", fontsize=9)

            # Redraw canvas
            self.figure.tight_layout()
            self.canvas.draw()

            # Update info label
            total_hours = sum(typing_hours)
            info_text = (
                f"Showing: {len(data_points)} {self.current_granularity.value}(s) | "
                f"Total: {total_hours:.1f} hours"
            )
            self.info_label.setText(info_text)
            log.info(f"Graph updated successfully: {info_text}")
        except Exception as e:
            log.error(f"Error updating graph: {e}")
            log.error(traceback.format_exc())
