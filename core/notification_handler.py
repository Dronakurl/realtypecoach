"""Notification handler for daily summaries and exceptional bursts."""

import time
import threading
import logging
from typing import Callable, Optional
from datetime import datetime, timedelta

from PySide6.QtCore import QObject, Signal

from core.models import DailySummary, WorstLetterChange


log = logging.getLogger("realtypecoach.notification")


class NotificationHandler(QObject):
    """Handles notifications for bursts and daily summaries."""

    signal_daily_summary = Signal(object)  # DailySummary object
    signal_exceptional_burst = Signal(float)
    signal_worst_letter_changed = Signal(object)  # WorstLetterChange object

    def __init__(
        self,
        summary_getter: Callable[[str], Optional[tuple]],
        storage=None,
        min_burst_ms: int = 10000,
        threshold_days: int = 30,
        threshold_update_sec: int = 300,
    ):
        """Initialize notification handler.

        Args:
            summary_getter: Function to get daily summary for a date
            storage: Storage instance for accessing burst history
            min_burst_ms: Minimum burst duration for notification (milliseconds)
            threshold_days: Lookback period for 95th percentile calculation (days)
            threshold_update_sec: How often to update threshold (seconds)
        """
        super().__init__()
        self.summary_getter = summary_getter
        self.storage = storage
        self.min_burst_ms = min_burst_ms
        self.threshold_days = threshold_days
        self.update_interval_sec = threshold_update_sec

        self.running = False
        self._stop_event = threading.Event()
        self.scheduler_thread: Optional[threading.Thread] = None
        self.threshold_thread: Optional[threading.Thread] = None

        self.notification_hour = 18
        self.notification_minute = 0
        self.last_notification_date: Optional[str] = None

        # Dynamic threshold based on 95th percentile
        self.percentile_95_threshold = 60.0  # Default starting threshold
        self.last_threshold_update = 0
        self._lock = threading.Lock()

        # Worst letter notification config
        self.worst_letter_notifications_enabled = True

        # Daily summary config
        self.daily_summary_enabled = True

    def start(self) -> None:
        """Start notification scheduler."""
        if self.running:
            return

        self.running = True
        self._stop_event.clear()

        # Start daily summary scheduler
        self.scheduler_thread = threading.Thread(
            target=self._run_scheduler, daemon=True
        )
        self.scheduler_thread.start()

        # Start threshold update thread
        self.threshold_thread = threading.Thread(
            target=self._run_threshold_updater, daemon=True
        )
        self.threshold_thread.start()

        # Initial threshold calculation
        self._update_threshold()

    def stop(self) -> None:
        """Stop notification scheduler."""
        self.running = False
        self._stop_event.set()
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=2)
        if self.threshold_thread:
            self.threshold_thread.join(timeout=2)

    def notify_exceptional_burst(
        self, wpm: float, key_count: int, duration_ms: int
    ) -> None:
        """Notify on exceptional burst.

        Args:
            wpm: Words per minute achieved
            key_count: Number of keystrokes
            duration_ms: Burst duration in milliseconds
        """
        # Only notify for bursts lasting at least minimum duration
        if duration_ms < self.min_burst_ms:
            return

        # Check if this burst is exceptional (above 95th percentile threshold)
        with self._lock:
            if wpm >= self.percentile_95_threshold:
                pass
            else:
                return

        self.signal_exceptional_burst.emit(wpm)

    def check_and_notify_worst_letter_change(self, change: WorstLetterChange) -> None:
        """Check if worst letter notification should be sent and emit signal.

        Args:
            change: WorstLetterChange object with change data
        """

        if not self.worst_letter_notifications_enabled:
            return

        self.signal_worst_letter_changed.emit(change)

    def _update_threshold(self) -> None:
        """Update the 95th percentile threshold from burst history."""
        if not self.storage:
            return

        try:
            with self.storage._get_connection() as conn:
                cursor = conn.cursor()

                # Get bursts from the configured lookback period
                cutoff_time = int(
                    (datetime.now() - timedelta(days=self.threshold_days)).timestamp()
                    * 1000
                )

                cursor.execute(
                    """
                    SELECT avg_wpm FROM bursts
                    WHERE start_time >= ? AND duration_ms >= ?
                    ORDER BY avg_wpm ASC
                """,
                    (cutoff_time, self.min_burst_ms),
                )

                wpms = [row[0] for row in cursor.fetchall()]

                if len(wpms) >= 20:
                    # Calculate 95th percentile (SQL already sorted)
                    percentile_index = int(len(wpms) * 0.95)
                    with self._lock:
                        self.percentile_95_threshold = wpms[percentile_index]
                elif len(wpms) > 0:
                    # Not enough data, use max + 10%
                    with self._lock:
                        self.percentile_95_threshold = max(wpms) * 1.1
                else:
                    # No data yet, use default
                    with self._lock:
                        self.percentile_95_threshold = 60.0

                self.last_threshold_update = time.time()

        except Exception as e:
            log.error(f"Error updating threshold: {e}")

    def _run_threshold_updater(self) -> None:
        """Background thread to update threshold periodically."""
        while not self._stop_event.is_set():
            self._stop_event.wait(self.update_interval_sec)
            if not self._stop_event.is_set():
                self._update_threshold()

    def _run_scheduler(self) -> None:
        """Background scheduler for daily notifications."""
        while not self._stop_event.is_set():
            now = datetime.now()

            if (
                self.daily_summary_enabled
                and now.hour == self.notification_hour
                and now.minute == self.notification_minute
            ):
                self._send_daily_summary(now.strftime("%Y-%m-%d"))
                # Wait until minute passes to avoid duplicate
                self._stop_event.wait(60)
                continue

            # Check every 30 seconds
            self._stop_event.wait(30)

    def _send_daily_summary(self, date: str) -> None:
        """Send daily summary notification.

        Args:
            date: Date string (YYYY-MM-DD)
        """
        with self._lock:
            if date == self.last_notification_date:
                return

        summary = self.summary_getter(date)
        if not summary:
            return

        (
            total_keystrokes,
            total_bursts,
            avg_wpm,
            slowest_keycode,
            slowest_key_name,
            total_typing_sec,
            summary_sent,
        ) = summary

        if summary_sent:
            return

        typing_hours = total_typing_sec // 3600
        typing_minutes = (total_typing_sec % 3600) // 60

        time_str = (
            f"{typing_hours}h {typing_minutes}m"
            if typing_hours > 0
            else f"{typing_minutes}m"
        )

        title = f"📊 Daily Typing Summary ({date})"
        message = f"""
━━━━━━━━━━━━━━━━━━━━
Keystrokes: {total_keystrokes:,}
Typing time: {time_str}
Average WPM: {avg_wpm:.1f}
Slowest key: '{slowest_key_name}' (avg)
━━━━━━━━━━━━━━━━━━━━
        """

        summary_obj = DailySummary(
            date=date,
            title=title,
            message=message,
            slowest_key=slowest_key_name,
            avg_wpm=str(int(avg_wpm)),
            keystrokes=f"{total_keystrokes:,} keystrokes",
        )

        self.signal_daily_summary.emit(summary_obj)

        with self._lock:
            self.last_notification_date = date

    def set_notification_time(self, hour: int = 18, minute: int = 0) -> None:
        """Set daily notification time.

        Args:
            hour: Hour (0-23)
            minute: Minute (0-59)
        """
        self.notification_hour = max(0, min(23, hour))
        self.notification_minute = max(0, min(59, minute))
