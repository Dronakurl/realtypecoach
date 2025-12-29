"""Configuration management for RealTypeCoach."""

import sqlite3
from pathlib import Path
from typing import Any, Optional


DEFAULT_SETTINGS = {
    'burst_timeout_ms': '1000',
    'word_boundary_timeout_ms': '1000',
    'burst_duration_calculation': 'total_time',
    'active_time_threshold_ms': '500',
    'high_score_min_duration_ms': '10000',
    'exceptional_wpm_threshold': '120',
    'password_exclusion': 'True',
    'notifications_enabled': 'True',
    'slowest_keys_count': '10',
    'data_retention_days': '90',
    'keyboard_layout': 'auto',
    'notification_time_hour': '18',
    'notification_time_minute': '0',
}


class Config:
    """Configuration manager using SQLite for persistence."""

    def __init__(self, db_path: Path):
        """Initialize config with database connection.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
        self._init_settings_table()

    def _init_settings_table(self) -> None:
        """Create settings table if not exists."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            ''')
            conn.commit()

            for key, value in DEFAULT_SETTINGS.items():
                conn.execute('''
                    INSERT OR IGNORE INTO settings (key, value)
                    VALUES (?, ?)
                ''', (key, value))
            conn.commit()

    def get(self, key: str, default: Optional[Any] = None) -> Any:
        """Get configuration value.

        Args:
            key: Setting key
            default: Default value if not found (uses DEFAULT_SETTINGS if None)

        Returns:
            Setting value
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
            result = cursor.fetchone()
            if result:
                return self._parse_value(result[0])
            if default is not None:
                return default
            return DEFAULT_SETTINGS.get(key)

    def get_int(self, key: str, default: Optional[int] = None) -> int:
        """Get integer configuration value."""
        value = self.get(key, default)
        try:
            return int(value)
        except (ValueError, TypeError):
            fallback = DEFAULT_SETTINGS.get(key, default)
            if fallback is not None:
                return int(fallback)
            return 0

    def get_float(self, key: str, default: Optional[float] = None) -> float:
        """Get float configuration value."""
        value = self.get(key, default)
        try:
            return float(value)
        except (ValueError, TypeError):
            fallback = DEFAULT_SETTINGS.get(key, default)
            if fallback is not None:
                return float(fallback)
            return 0.0

    def get_bool(self, key: str, default: Optional[bool] = None) -> bool:
        """Get boolean configuration value."""
        value = self.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ('true', '1', 'yes', 'on')
        fallback = DEFAULT_SETTINGS.get(key, default)
        if fallback is not None:
            return bool(fallback)
        return False

    def set(self, key: str, value: Any) -> None:
        """Set configuration value.

        Args:
            key: Setting key
            value: Setting value
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO settings (key, value)
                VALUES (?, ?)
            ''', (key, str(value)))
            conn.commit()

    def get_all(self) -> dict[str, Any]:
        """Get all settings as dictionary."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT key, value FROM settings')
            settings = {row[0]: self._parse_value(row[1]) for row in cursor.fetchall()}
        return settings

    def _parse_value(self, value: str) -> Any:
        """Parse string value to appropriate type."""
        try:
            return int(value)
        except ValueError:
            pass

        try:
            return float(value)
        except ValueError:
            pass

        if value.lower() in ('true', '1', 'yes', 'on'):
            return True
        if value.lower() in ('false', '0', 'no', 'off'):
            return False

        return value
