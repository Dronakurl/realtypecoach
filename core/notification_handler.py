"""Notification handler for daily summaries and exceptional bursts."""

import time
import threading
from typing import Callable, Optional
from datetime import datetime

from PyQt5.QtCore import QObject, pyqtSignal


class NotificationHandler(QObject):
    """Handles notifications for bursts and daily summaries."""

    signal_daily_summary = pyqtSignal(str, str, str, str, str, str, str)
    signal_exceptional_burst = pyqtSignal(float)

    def __init__(self, summary_getter: Callable[[str], Optional[tuple]],
                 exceptional_threshold: float = 120.0):
        """Initialize notification handler.

        Args:
            summary_getter: Function to get daily summary for a date
            exceptional_threshold: WPM threshold for exceptional bursts
        """
        super().__init__()
        self.summary_getter = summary_getter
        self.exceptional_threshold = exceptional_threshold
        self.running = False
        self.scheduler_thread: Optional[threading.Thread] = None

        self.notification_hour = 18
        self.notification_minute = 0
        self.last_notification_date: Optional[str] = None

    def start(self) -> None:
        """Start notification scheduler."""
        if self.running:
            return

        self.running = True
        self.scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.scheduler_thread.start()

    def stop(self) -> None:
        """Stop notification scheduler."""
        self.running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)

    def notify_exceptional_burst(self, wpm: float, key_count: int,
                                    duration_sec: float) -> None:
        """Notify on exceptional burst.

        Args:
            wpm: Words per minute achieved
            key_count: Number of keystrokes
            duration_sec: Burst duration in seconds
        """
        if wpm >= self.exceptional_threshold and duration_sec >= 10:
            message = f"🚀 Exceptional typing speed!\n"
            message += f"{wpm:.1f} WPM ({key_count} keys in {duration_sec:.1f}s)"
            self.signal_exceptional_burst.emit(wpm)

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
