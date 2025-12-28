"""Notification handler for daily summaries and exceptional bursts."""

import time
import threading
from typing import Callable, Optional, List
from datetime import datetime, timedelta

from PyQt5.QtCore import QObject, pyqtSignal


class NotificationHandler(QObject):
    """Handles notifications for bursts and daily summaries."""

    signal_daily_summary = pyqtSignal(str, str, str, str, str, str, str)
    signal_exceptional_burst = pyqtSignal(float)

    def __init__(self, summary_getter: Callable[[str], Optional[tuple]],
                 storage=None,
                 update_interval_sec: int = 300):
        """Initialize notification handler.

        Args:
            summary_getter: Function to get daily summary for a date
            storage: Storage instance for accessing burst history
            update_interval_sec: How often to update threshold (default 300 = 5 minutes)
        """
        super().__init__()
        self.summary_getter = summary_getter
        self.storage = storage
        self.update_interval_sec = update_interval_sec

        self.running = False
        self.scheduler_thread: Optional[threading.Thread] = None
        self.threshold_thread: Optional[threading.Thread] = None

        self.notification_hour = 18
        self.notification_minute = 0
        self.last_notification_date: Optional[str] = None

        # Dynamic threshold based on 95th percentile
        self.percentile_95_threshold = 60.0  # Default starting threshold
        self.last_threshold_update = 0

    def start(self) -> None:
        """Start notification scheduler."""
        if self.running:
            return

        self.running = True

        # Start daily summary scheduler
        self.scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.scheduler_thread.start()

        # Start threshold update thread
        self.threshold_thread = threading.Thread(target=self._run_threshold_updater, daemon=True)
        self.threshold_thread.start()

        # Initial threshold calculation
        self._update_threshold()

    def stop(self) -> None:
        """Stop notification scheduler."""
        self.running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
        if self.threshold_thread:
            self.threshold_thread.join(timeout=5)

    def notify_exceptional_burst(self, wpm: float, key_count: int,
                                    duration_sec: float) -> None:
        """Notify on exceptional burst.

        Args:
            wpm: Words per minute achieved
            key_count: Number of keystrokes
            duration_sec: Burst duration in seconds
        """
        # Only notify for bursts lasting at least 10 seconds
        if duration_sec < 10:
            return

        # Check if this burst is exceptional (above 95th percentile threshold)
        if wpm >= self.percentile_95_threshold:
            message = f"🚀 Exceptional typing speed!\n"
            message += f"{wpm:.1f} WPM ({key_count} keys in {duration_sec:.1f}s)"
            message += f"\nThreshold: {self.percentile_95_threshold:.1f} WPM (95th percentile)"
            self.signal_exceptional_burst.emit(wpm)

    def _update_threshold(self) -> None:
        """Update the 95th percentile threshold from burst history."""
        if not self.storage:
            return

        try:
            import sqlite3
            with sqlite3.connect(self.storage.db_path) as conn:
                cursor = conn.cursor()

                # Get bursts from the last 30 days
                thirty_days_ago = int((datetime.now() - timedelta(days=30)).timestamp() * 1000)

                cursor.execute('''
                    SELECT avg_wpm FROM bursts
                    WHERE start_time >= ? AND duration_ms >= 10000
                    ORDER BY avg_wpm ASC
                ''', (thirty_days_ago,))

                wpms = [row[0] for row in cursor.fetchall()]

                if len(wpms) >= 20:
                    # Calculate 95th percentile
                    wpms.sort()
                    percentile_index = int(len(wpms) * 0.95)
                    self.percentile_95_threshold = wpms[percentile_index]
                elif len(wpms) > 0:
                    # Not enough data, use max + 10%
                    self.percentile_95_threshold = max(wpms) * 1.1
                else:
                    # No data yet, use default
                    self.percentile_95_threshold = 60.0

                self.last_threshold_update = time.time()

        except Exception as e:
            print(f"Error updating threshold: {e}")

    def _run_threshold_updater(self) -> None:
        """Background thread to update threshold every 5 minutes."""
        while self.running:
            time.sleep(self.update_interval_sec)
            self._update_threshold()

    def _run_scheduler(self) -> None:
        """Background scheduler for daily notifications."""
        while self.running:
            now = datetime.now()
            current_time = now.time()

            if now.hour == self.notification_hour and now.minute == self.notification_minute:
                self._send_daily_summary(now.strftime('%Y-%m-%d'))
                time.sleep(60)  # Wait 1 minute to avoid duplicate

            time.sleep(30)  # Check every 30 seconds

    def _send_daily_summary(self, date: str) -> None:
        """Send daily summary notification.

        Args:
            date: Date string (YYYY-MM-DD)
        """
        if date == self.last_notification_date:
            return

        summary = self.summary_getter(date)
        if not summary:
            return

        (total_keystrokes, total_bursts, avg_wpm,
         slowest_keycode, slowest_key_name, total_typing_sec,
         summary_sent) = summary

        if summary_sent:
            return

        typing_hours = total_typing_sec // 3600
        typing_minutes = (total_typing_sec % 3600) // 60

        time_str = f"{typing_hours}h {typing_minutes}m" if typing_hours > 0 else f"{typing_minutes}m"

        title = f"📊 Daily Typing Summary ({date})"
        message = f"""
━━━━━━━━━━━━━━━━━━━━
Keystrokes: {total_keystrokes:,}
Typing time: {time_str}
Average WPM: {avg_wpm:.1f}
Slowest key: '{slowest_key_name}' (avg)
━━━━━━━━━━━━━━━━━━━━
        """

        self.signal_daily_summary.emit(date, title, message,
                                       slowest_key_name, str(int(avg_wpm)),
                                       f"{total_keystrokes:,} keystrokes")

        self.last_notification_date = date

    def set_notification_time(self, hour: int = 18, minute: int = 0) -> None:
        """Set daily notification time.

        Args:
            hour: Hour (0-23)
            minute: Minute (0-59)
        """
        self.notification_hour = max(0, min(23, hour))
        self.notification_minute = max(0, min(59, minute))
