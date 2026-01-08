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
from PySide6.QtCore import QTimer
import pyqtgraph as pg
from pyqtgraph import GraphicsLayoutWidget, BarGraphItem
from core.models import TypingTimeDataPoint


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
        self.granularity_combo.currentIndexChanged.connect(self.on_granularity_changed)
        controls_layout.addWidget(self.granularity_combo)

        # Refresh button
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.request_data)
        controls_layout.addWidget(refresh_btn)

        controls_layout.addStretch()
        layout.addLayout(controls_layout)

        # PyQtGraph GraphicsLayoutWidget for stacked plots
        self.plot_widget = GraphicsLayoutWidget()

        # Create two plots with shared X-axis
        self.plot_time = self.plot_widget.addPlot(row=0, col=0)
        self.plot_time.setLabel("left", "Typing Time (hours)")
        self.plot_time.showGrid(x=True, y=True, alpha=0.3)
        self.plot_time.showButtons()
        # Disable automatic scientific notation suffix
        self.plot_time.getAxis("left").enableAutoSIPrefix(False)
        # Y-axis starts at 0, auto-range enabled
        self.plot_time.setYRange(0, 1, padding=0.1)
        # Hide X-axis on top plot (bottom plot shows it for both)
        self.plot_time.hideAxis('bottom')

        self.plot_wpm = self.plot_widget.addPlot(row=1, col=0)
        self.plot_wpm.setLabel("left", "Average WPM")
        self.plot_wpm.setLabel("bottom", "Time Period")
        self.plot_wpm.showGrid(x=True, y=True, alpha=0.3)
        self.plot_wpm.showButtons()
        # Y-axis starts at 0 for WPM as well
        self.plot_wpm.setYRange(0, 100, padding=0.1)

        # Link X-axes
        self.plot_wpm.setXLink(self.plot_time)

        # Create bar chart item for typing time (initially empty)
        self.bar_item = BarGraphItem(x=[], height=[], width=0.6, brush=(50, 150, 200))
        self.plot_time.addItem(self.bar_item)

        # Create plot item for WPM line chart
        self.plot_wpm_item = self.plot_wpm.plot(
            pen=pg.mkPen(color=(80, 200, 120), width=2), symbol="o", symbolSize=5
        )

        layout.addWidget(self.plot_widget)

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
        self._update_timer.timeout.connect(
            lambda: self._update_granularity(granularity)
        )
        self._update_timer.start(300)  # 300ms debounce

    def _update_granularity(self, granularity: TimeGranularity) -> None:
        """Update graph with new granularity.

        Args:
            granularity: New time granularity
        """
        self.current_granularity = granularity

        # Request new data
        self.request_data()

    def set_data_callback(
        self, callback: Callable[[str], None], load_immediately: bool = False
    ) -> None:
        """Set callback for requesting new data.

        The callback will be called with granularity string ("day", "week", "month", "quarter")
        whenever new data is needed.

        Args:
            callback: Function to call with granularity string
            load_immediately: If True, load data immediately. If False, wait for explicit request.
        """
        self._data_callback = callback
        # Load initial data only if requested
        if load_immediately and self._data_callback:
            from PySide6.QtCore import QTimer

            QTimer.singleShot(
                0, lambda: self._data_callback(self.current_granularity.value)
            )

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

            if not data_points:
                log.warning("No data points received, showing 'No data available'")
                self.bar_item.setOpts(x=[], height=[])
                self.plot_wpm_item.setData([], [])
                self.info_label.setText("Showing: No data")
                return

            # Extract data
            period_labels = [dp.period_label for dp in data_points]
            typing_hours = [
                dp.total_typing_ms / 3600000.0 for dp in data_points
            ]  # Convert to hours
            avg_wpm = [dp.avg_wpm for dp in data_points]

            # Create x-axis indices
            x_indices = list(range(len(period_labels)))

            # Update bar chart for typing time
            self.bar_item.setOpts(x=x_indices, height=typing_hours)

            # Auto-scale Y-axis for typing time, starting from 0
            max_hours = max(typing_hours) if typing_hours else 1
            self.plot_time.setYRange(0, max_hours * 1.1, padding=0)

            # Update line chart for WPM
            self.plot_wpm_item.setData(x_indices, avg_wpm)

            # Auto-scale Y-axis for WPM, starting from 0
            max_wpm = max(avg_wpm) if avg_wpm else 100
            self.plot_wpm.setYRange(0, max_wpm * 1.1, padding=0)

            # Format labels more compactly for days mode
            display_labels = period_labels
            if self.current_granularity == TimeGranularity.DAY:
                from datetime import datetime
                display_labels = []
                for label in period_labels:
                    try:
                        dt = datetime.strptime(label, "%Y-%m-%d")
                        display_labels.append(dt.strftime("%b %d"))
                    except Exception:
                        display_labels.append(label)

            # Set X-axis ticks with labels (show fewer ticks to prevent overlap)
            if len(data_points) > 7:
                # Show every Nth label (target ~6 ticks instead of ~10)
                step = max(1, len(display_labels) // 6)
                ticks = [
                    (i, display_labels[i]) for i in range(0, len(display_labels), step)
                ]
                self.plot_wpm.getAxis("bottom").setTicks([ticks])
            else:
                # Show all labels
                ticks = [(i, display_labels[i]) for i in range(len(display_labels))]
                self.plot_wpm.getAxis("bottom").setTicks([ticks])

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
