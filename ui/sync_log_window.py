"""Sync audit log viewer window."""

import json
import logging
from datetime import UTC, datetime

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDateEdit,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

log = logging.getLogger("realtypecoach.sync_log_window")


class SyncLogWindow(QDialog):
    """Dialog for viewing sync audit log history and statistics."""

    def __init__(self, storage, parent=None):
        """Initialize sync log viewer window.

        Args:
            storage: Storage instance
            parent: Parent widget
        """
        super().__init__(parent)
        self.storage = storage
        self.available_machines = []
        self.date_filter_ms = None
        self.init_ui()
        self.populate_machine_filter()
        self.load_logs()

    def init_ui(self):
        """Initialize user interface."""
        self.setWindowTitle("Sync Audit Log")
        self.setMinimumSize(900, 600)
        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)

        layout = QVBoxLayout()

        # Create tab widget
        self.tabs = QTabWidget()
        self.logs_tab = self.create_logs_tab()
        self.stats_tab = self.create_stats_tab()
        self.tabs.addTab(self.logs_tab, "Log History")
        self.tabs.addTab(self.stats_tab, "Statistics")
        layout.addWidget(self.tabs)

        # Button layout
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.load_logs)
        button_layout.addWidget(refresh_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def create_logs_tab(self):
        """Create log history tab.

        Returns:
            QWidget with log history table
        """
        widget = QWidget()
        layout = QVBoxLayout()

        # Filter controls - single row layout
        filter_group = QGroupBox("Filters")
        filter_layout = QHBoxLayout()

        # Machine name filter
        filter_layout.addWidget(QLabel("Machine:"))
        self.machine_combo = QComboBox()
        self.machine_combo.setMinimumWidth(150)
        self.machine_combo.currentTextChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.machine_combo)

        # Date to filter
        filter_layout.addWidget(QLabel("Entries before:"))
        self.date_to_edit = QLineEdit()
        self.date_to_edit.setPlaceholderText("No filter")
        self.date_to_edit.setReadOnly(True)
        self.date_to_edit.setMinimumWidth(120)
        self.date_to_edit.mousePressEvent = self.on_date_edit_clicked
        filter_layout.addWidget(self.date_to_edit)

        # Hide empty checkbox
        self.hide_empty_checkbox = QCheckBox("Hide empty")
        self.hide_empty_checkbox.stateChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.hide_empty_checkbox)

        filter_layout.addStretch()

        # Clear button
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.clear_filters)
        filter_layout.addWidget(clear_btn)

        filter_group.setLayout(filter_layout)
        layout.addWidget(filter_group)

        # Create table
        self.logs_table = QTableWidget()
        self.logs_table.setColumnCount(7)
        self.logs_table.setHorizontalHeaderLabels(
            ["Timestamp", "Machine", "Pushed", "Pulled", "Merged", "Duration", "Status"]
        )
        self.logs_table.setSortingEnabled(False)
        self.logs_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.logs_table.setSelectionMode(QTableWidget.SingleSelection)
        self.logs_table.cellDoubleClicked.connect(self.show_log_details)

        # Set column widths
        self.logs_table.setColumnWidth(0, 160)  # Timestamp
        self.logs_table.setColumnWidth(1, 150)  # Machine
        self.logs_table.setColumnWidth(2, 70)  # Pushed
        self.logs_table.setColumnWidth(3, 70)  # Pulled
        self.logs_table.setColumnWidth(4, 70)  # Merged
        self.logs_table.setColumnWidth(5, 80)  # Duration
        self.logs_table.setColumnWidth(6, 100)  # Status

        layout.addWidget(self.logs_table)
        widget.setLayout(layout)

        # Add hint label
        hint_label = QLabel("💡 Double-click a row to see per-table breakdown")
        hint_label.setStyleSheet("color: #666; font-style: italic; padding: 5px;")
        layout.addWidget(hint_label)

        return widget

    def populate_machine_filter(self):
        """Populate machine name filter from available sync logs."""
        try:
            # Get unique machine names from sync logs
            logs = self.storage.get_sync_logs(limit=10000)
            machines = sorted(set(log.get("machine_name", "unknown") for log in logs))
            self.available_machines = machines

            self.machine_combo.clear()
            self.machine_combo.addItem("All Machines")
            self.machine_combo.addItems(machines)
        except Exception as e:
            log.error(f"Failed to populate machine filter: {e}")

    def on_date_edit_clicked(self, event):
        """Handle date edit click - show date picker dialog."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Select Date")
        dialog.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        dialog.setModal(True)

        layout = QVBoxLayout()

        date_edit = QDateEdit()
        date_edit.setCalendarPopup(True)
        date_edit.setDate(QDate.currentDate())
        date_edit.setMinimumWidth(250)
        layout.addWidget(date_edit)

        button_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("Cancel")

        ok_btn.clicked.connect(lambda: self.date_selected(dialog, date_edit.date()))
        cancel_btn.clicked.connect(dialog.reject)

        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        dialog.setLayout(layout)

        # Position dialog below the date edit field
        pos = self.date_to_edit.mapToGlobal(self.date_to_edit.rect().bottomLeft())
        dialog.move(pos)

        dialog.exec()

    def date_selected(self, dialog, qdate):
        """Handle date selection from picker."""
        if qdate.isValid():
            # End of the selected day (23:59:59)
            dt = datetime(qdate.year(), qdate.month(), qdate.day(), 23, 59, 59, tzinfo=UTC)
            self.date_filter_ms = int(dt.timestamp() * 1000)
            self.date_to_edit.setText(qdate.toString("yyyy-MM-dd"))
            self.apply_filters()
        dialog.accept()

    def apply_filters(self):
        """Apply filters and reload logs."""
        try:
            # Block signals to prevent recursive calls
            self.machine_combo.blockSignals(True)
            self.hide_empty_checkbox.blockSignals(True)

            # Get filter values
            machine_name = None
            if self.machine_combo.currentIndex() > 0:
                machine_name = self.machine_combo.currentText()

            date_to = self.date_filter_ms
            hide_empty = self.hide_empty_checkbox.isChecked()

            # Load logs with filters
            logs = self.storage.get_sync_logs(
                limit=10000,
                machine_name=machine_name,
                date_to=date_to,
                hide_empty=hide_empty,
            )
            self.populate_logs_table(logs)
        except Exception as e:
            log.error(f"Failed to apply filters: {e}")
        finally:
            # Unblock signals
            self.machine_combo.blockSignals(False)
            self.hide_empty_checkbox.blockSignals(False)

    def clear_filters(self):
        """Clear all filters and reload logs."""
        self.machine_combo.setCurrentIndex(0)
        self.date_to_edit.clear()
        self.date_filter_ms = None
        self.hide_empty_checkbox.setChecked(False)

    def create_stats_tab(self):
        """Create statistics tab.

        Returns:
            QWidget with statistics display
        """
        widget = QWidget()
        layout = QVBoxLayout()

        # Aggregate stats group
        stats_group = QGroupBox("Overall Statistics")
        stats_layout = QVBoxLayout()
        self.stats_label = QLabel("No sync data available")
        self.stats_label.setTextFormat(Qt.RichText)
        stats_layout.addWidget(self.stats_label)
        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)

        # Recent syncs with breakdown
        recent_group = QGroupBox("Recent Syncs (Per-Table Breakdown)")
        recent_layout = QVBoxLayout()
        self.recent_label = QLabel()
        self.recent_label.setTextFormat(Qt.RichText)
        self.recent_label.setWordWrap(True)
        recent_layout.addWidget(self.recent_label)
        recent_group.setLayout(recent_layout)
        layout.addWidget(recent_group)

        layout.addStretch()
        widget.setLayout(layout)

        return widget

    def load_logs(self):
        """Load sync logs from database and populate UI."""
        try:
            logs = self.storage.get_sync_logs(limit=200)
            self.populate_logs_table(logs)
            self.update_statistics(logs)
        except Exception as e:
            log.error(f"Failed to load sync logs: {e}")
            self.logs_table.setRowCount(0)
            self.stats_label.setText("❌ Failed to load sync logs")

    def populate_logs_table(self, logs):
        """Populate logs table with data.

        Args:
            logs: List of sync log dictionaries
        """
        self.logs_table.setRowCount(len(logs))

        for row, log_entry in enumerate(logs):
            # Timestamp
            timestamp_ms = log_entry.get("timestamp", 0)
            timestamp_str = self.format_timestamp(timestamp_ms)
            self.logs_table.setItem(row, 0, QTableWidgetItem(timestamp_str))

            # Machine name
            machine_name = log_entry.get("machine_name", "unknown")
            self.logs_table.setItem(row, 1, QTableWidgetItem(machine_name))

            # Pushed
            pushed = log_entry.get("pushed", 0)
            self.logs_table.setItem(row, 2, QTableWidgetItem(str(pushed)))

            # Pulled
            pulled = log_entry.get("pulled", 0)
            self.logs_table.setItem(row, 3, QTableWidgetItem(str(pulled)))

            # Merged
            merged = log_entry.get("merged", 0)
            self.logs_table.setItem(row, 4, QTableWidgetItem(str(merged)))

            # Duration
            duration_ms = log_entry.get("duration_ms", 0)
            duration_str = f"{duration_ms / 1000:.1f}s"
            self.logs_table.setItem(row, 5, QTableWidgetItem(duration_str))

            # Status
            error = log_entry.get("error")
            if error:
                status = "❌ Error"
                status_item = QTableWidgetItem(status)
                status_item.setForeground(Qt.GlobalColor.red)
            else:
                status = "✅ Success"
                status_item = QTableWidgetItem(status)
                status_item.setForeground(Qt.GlobalColor.green)
            self.logs_table.setItem(row, 6, status_item)

            # Store log entry for detail view
            self.logs_table.item(row, 0).setData(Qt.UserRole, log_entry)

    def update_statistics(self, logs):
        """Update statistics tab.

        Args:
            logs: List of sync log dictionaries
        """
        try:
            # Get aggregate stats
            stats = self.storage.get_sync_log_stats()

            total_syncs = stats.get("total_syncs", 0)
            total_pushed = stats.get("total_pushed", 0)
            total_pulled = stats.get("total_pulled", 0)
            total_merged = stats.get("total_merged", 0)
            last_sync_ms = stats.get("last_sync", 0)

            # Update aggregate stats
            if total_syncs > 0:
                last_sync_str = self.format_timestamp(last_sync_ms)
                stats_html = f"""
                <h3>Sync Overview</h3>
                <p><b>Total Syncs:</b> {total_syncs}</p>
                <p><b>Total Records Pushed:</b> {total_pushed}</p>
                <p><b>Total Records Pulled:</b> {total_pulled}</p>
                <p><b>Total Records Merged:</b> {total_merged}</p>
                <p><b>Last Sync:</b> {last_sync_str}</p>
                """
                self.stats_label.setText(stats_html)
            else:
                self.stats_label.setText("No sync data available yet")

            # Update recent syncs with breakdown
            recent_logs = logs[:10]  # Show last 10 syncs
            if recent_logs:
                recent_html = "<h3>Recent Sync Details</h3>"
                for log_entry in recent_logs:
                    timestamp_str = self.format_timestamp(log_entry.get("timestamp", 0))
                    machine = log_entry.get("machine_name", "unknown")
                    error = log_entry.get("error")

                    if error:
                        recent_html += (
                            f"<p><b>{timestamp_str}</b> - {machine}<br>❌ Error: {error}</p>"
                        )
                    else:
                        recent_html += f"<p><b>{timestamp_str}</b> - {machine}<br>"

                        # Parse table breakdown
                        table_breakdown_json = log_entry.get("table_breakdown", "{}")
                        try:
                            table_breakdown = json.loads(table_breakdown_json)
                            if table_breakdown:
                                recent_html += "Per-table breakdown:<br>"
                                for table, stats in table_breakdown.items():
                                    pushed = stats.get("pushed", 0)
                                    pulled = stats.get("pulled", 0)
                                    merged = stats.get("merged", 0)
                                    if pushed or pulled or merged:
                                        recent_html += (
                                            f"  • {table}: ↑{pushed} ↓{pulled} ⇄{merged}<br>"
                                        )
                                recent_html = recent_html.rstrip("<br>") + "</p>"
                            else:
                                recent_html += "No per-table data available</p>"
                        except json.JSONDecodeError:
                            recent_html += "No per-table data available</p>"

                self.recent_label.setText(recent_html)
            else:
                self.recent_label.setText("No recent syncs")

        except Exception as e:
            log.error(f"Failed to update statistics: {e}")
            self.stats_label.setText("❌ Failed to load statistics")

    def show_log_details(self, row, column):
        """Show details for a log entry.

        Args:
            row: Table row
            column: Table column (unused)
        """
        item = self.logs_table.item(row, 0)
        if not item:
            return

        log_entry = item.data(Qt.UserRole)
        if not log_entry:
            return

        # Create details dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Sync Log Details")
        dialog.setMinimumSize(500, 400)
        dialog.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)

        layout = QVBoxLayout()

        # Details text
        details_text = QTextEdit()
        details_text.setReadOnly(True)

        # Format details
        timestamp_str = self.format_timestamp(log_entry.get("timestamp", 0))
        machine = log_entry.get("machine_name", "unknown")
        pushed = log_entry.get("pushed", 0)
        pulled = log_entry.get("pulled", 0)
        merged = log_entry.get("merged", 0)
        duration_ms = log_entry.get("duration_ms", 0)
        error = log_entry.get("error")

        details_html = "<h2>Sync Details</h2>"
        details_html += f"<p><b>Timestamp:</b> {timestamp_str}</p>"
        details_html += f"<p><b>Machine:</b> {machine}</p>"
        details_html += f"<p><b>Pushed:</b> {pushed} records</p>"
        details_html += f"<p><b>Pulled:</b> {pulled} records</p>"
        details_html += f"<p><b>Merged:</b> {merged} records</p>"
        details_html += f"<p><b>Duration:</b> {duration_ms / 1000:.2f} seconds</p>"

        if error:
            details_html += f"<p><b>Error:</b> {error}</p>"

        # Parse and display table breakdown
        table_breakdown_json = log_entry.get("table_breakdown", "{}")
        try:
            table_breakdown = json.loads(table_breakdown_json)
            if table_breakdown:
                details_html += "<h3>Per-Table Breakdown</h3>"
                details_html += "<table border='1' cellpadding='5'>"
                details_html += (
                    "<tr><th>Table</th><th>Pushed</th><th>Pulled</th><th>Merged</th></tr>"
                )
                for table, stats in table_breakdown.items():
                    pushed = stats.get("pushed", 0)
                    pulled = stats.get("pulled", 0)
                    merged = stats.get("merged", 0)
                    details_html += f"<tr><td>{table}</td><td>{pushed}</td><td>{pulled}</td><td>{merged}</td></tr>"
                details_html += "</table>"
        except json.JSONDecodeError:
            details_html += "<p><i>No per-table breakdown available</i></p>"

        details_text.setHtml(details_html)
        layout.addWidget(details_text)

        # Close button
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)

        dialog.setLayout(layout)
        dialog.exec()

    def format_timestamp(self, timestamp_ms: int) -> str:
        """Format timestamp for display.

        Args:
            timestamp_ms: Timestamp in milliseconds

        Returns:
            Formatted timestamp string
        """
        if not timestamp_ms:
            return "N/A"

        try:
            dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)
            return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        except Exception:
            return "Invalid timestamp"
