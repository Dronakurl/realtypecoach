"""Configuration management for RealTypeCoach."""

import json
import sqlcipher3 as sqlite3
from pathlib import Path
from typing import Any, Optional, List

from pydantic import BaseModel, ConfigDict, Field, field_validator
from utils.crypto import CryptoManager


class AppSettings(BaseModel):
    """Application settings with validation."""

    # Burst detection settings
    burst_timeout_ms: int = Field(
        default=1000,
        gt=0,
        description="Max pause between keystrokes before burst ends (ms)",
    )
    word_boundary_timeout_ms: int = Field(
        default=1000,
        gt=0,
        description="Max pause between letters before word splits (ms)",
    )
    burst_duration_calculation: str = Field(
        default="total_time",
        description="How to calculate burst duration (total_time or active_time)",
    )
    active_time_threshold_ms: int = Field(
        default=500,
        gt=0,
        description="For active_time method, max interval to count as active (ms)",
    )
    high_score_min_duration_ms: int = Field(
        default=10000,
        gt=0,
        description="Minimum duration for burst to qualify for high score (ms)",
    )
    min_burst_key_count: int = Field(
        default=10,
        ge=1,
        description="Minimum keystrokes required for burst to be recorded",
    )
    min_burst_duration_ms: int = Field(
        default=5000,
        gt=0,
        description="Minimum duration required for burst to be recorded (ms)",
    )

    # Data management
    data_retention_days: int = Field(
        default=-1, ge=-1, description="Days to keep data (-1 = keep forever)"
    )

    # Keyboard layout
    keyboard_layout: str = Field(
        default="auto", description="Keyboard layout identifier"
    )

    # Notification settings
    notification_time_hour: int = Field(
        default=18, ge=0, le=23, description="Daily notification hour (0-23)"
    )
    notification_min_burst_ms: int = Field(
        default=10000, gt=0, description="Min burst duration for notification (ms)"
    )
    notification_threshold_days: int = Field(
        default=30, ge=1, description="Days threshold for notification"
    )
    notification_threshold_update_sec: int = Field(
        default=300, ge=60, description="Update interval for notification (sec)"
    )
    worst_letter_notifications_enabled: bool = Field(
        default=True, description="Enable worst letter change notifications"
    )
    worst_letter_notification_debounce_min: int = Field(
        default=5,
        ge=1,
        le=60,
        description="Debounce time for worst letter notifications (minutes)",
    )

    # Dictionary settings
    dictionary_mode: str = Field(
        default="validate",
        description="Dictionary validation mode (validate or accept_all)",
    )
    enabled_languages: str = Field(
        default="en,de", description="Comma-separated language codes"
    )

    model_config = ConfigDict(extra="ignore", use_enum_values=True)

    @field_validator("active_time_threshold_ms")
    @classmethod
    def validate_active_threshold(cls, v, info):
        """Validate interdependent field relationships."""
        if "burst_timeout_ms" in info.data and v >= info.data["burst_timeout_ms"]:
            raise ValueError(
                f"active_time_threshold_ms ({v}) must be "
                f"less than burst_timeout_ms ({info.data['burst_timeout_ms']})"
            )
        return v


class Config:
    """Configuration manager using SQLite for persistence with Pydantic validation."""

    def __init__(self, db_path: Path):
        """Initialize config with database connection.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path

        # Initialize crypto manager
        self.crypto = CryptoManager(db_path)

        # For fresh installs, initialize encryption key first
        is_fresh_install = not db_path.exists()
        if is_fresh_install:
            try:
                self.crypto.initialize_database_key()
            except RuntimeError as e:
                # If key already exists, that's fine - user is doing a reinstall
                if "already exists" not in str(e):
                    raise

        self._init_settings_table()
        self._ensure_defaults()

    def _get_connection(self) -> sqlite3.Connection:
        """Create encrypted database connection."""
        encryption_key = self.crypto.get_key()
        if encryption_key is None:
            raise RuntimeError(
                "Database encryption key not found in keyring. "
                "Cannot access configuration database."
            )

        conn = sqlite3.connect(self.db_path)

        # Set encryption key (SQLCipher requires quotes around the hex literal)
        conn.execute(f"PRAGMA key = \"x'{encryption_key.hex()}'\"")

        # Verify access
        try:
            conn.execute("SELECT count(*) FROM sqlite_master")
        except sqlite3.DatabaseError as e:
            conn.close()
            raise RuntimeError(f"Cannot decrypt settings database: {e}")

        # Set encryption parameters
        conn.execute("PRAGMA cipher_memory_security = ON")
        conn.execute("PRAGMA cipher_page_size = 4096")
        conn.execute("PRAGMA cipher_kdf_iter = 256000")

        return conn

    def _init_settings_table(self) -> None:
        """Create settings table if not exists."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            conn.commit()

    def _ensure_defaults(self) -> None:
        """Ensure all default settings exist in database."""
        defaults = AppSettings().model_dump()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            for key, value in defaults.items():
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO settings (key, value)
                    VALUES (?, ?)
                """,
                    (key, self._serialize_value(value)),
                )
            conn.commit()

    def _serialize_value(self, value: Any) -> str:
        """Convert value to string for storage."""
        if isinstance(value, bool):
            return "True" if value else "False"
        if isinstance(value, (list, dict)):
            return json.dumps(value)
        return str(value)

    def _simple_parse(self, value: str) -> Any:
        """Simple fallback parsing without pydantic."""
        # Try JSON first (for lists/dicts)
        if value.startswith("[") or value.startswith("{"):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                pass

        # Try int
        try:
            return int(value)
        except ValueError:
            pass

        # Try float
        try:
            return float(value)
        except ValueError:
            pass

        # Boolean values
        if value.lower() in ("true", "1", "yes", "on"):
            return True
        if value.lower() in ("false", "0", "no", "off"):
            return False

        # Return as string
        return value

    def get(self, key: str, default: Optional[Any] = None) -> Any:
        """Get configuration value.

        Args:
            key: Setting key
            default: Default value if not found

        Returns:
            Setting value
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            result = cursor.fetchone()
            if result:
                raw_value = result[0]
                parsed = self._simple_parse(raw_value)
                # Validate through pydantic if key is in AppSettings
                if key in AppSettings.model_fields:
                    try:
                        settings = AppSettings(**{key: parsed})
                        return getattr(settings, key)
                    except Exception:
                        return parsed
                return parsed
            if default is not None:
                return default
            # Fall back to AppSettings default if key exists
            if key in AppSettings.model_fields:
                settings = AppSettings()
                return getattr(settings, key)
            return None

    def get_int(self, key: str, default: Optional[int] = None) -> int:
        """Get integer configuration value."""
        value = self.get(key, default)
        if isinstance(value, int):
            return value
        try:
            return int(value)
        except (ValueError, TypeError):
            settings = AppSettings()
            if hasattr(settings, key):
                return getattr(settings, key)
            return default if default is not None else 0

    def get_float(self, key: str, default: Optional[float] = None) -> float:
        """Get float configuration value."""
        value = self.get(key, default)
        if isinstance(value, float):
            return value
        try:
            return float(value)
        except (ValueError, TypeError):
            settings = AppSettings()
            if hasattr(settings, key):
                return float(getattr(settings, key))
            return default if default is not None else 0.0

    def get_bool(self, key: str, default: Optional[bool] = None) -> bool:
        """Get boolean configuration value."""
        value = self.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            # Handle integer values (1 = True, 0 = False)
            return bool(value)
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "on")
        # Fallback for any other type
        return bool(value) if value else False

    def set(self, key: str, value: Any) -> None:
        """Set configuration value with pydantic validation.

        Args:
            key: Setting key
            value: Setting value

        Raises:
            ValueError: If value fails validation
        """
        # Validate using pydantic if key is in AppSettings
        if key in AppSettings.model_fields:
            try:
                partial = {key: value}
                validated = AppSettings(**partial)
                value = getattr(validated, key)
            except Exception as e:
                raise ValueError(f"Invalid value for {key}: {e}")

        # Store value (validated or custom)
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO settings (key, value)
                VALUES (?, ?)
            """,
                (key, self._serialize_value(value)),
            )
            conn.commit()

    def get_all(self) -> dict[str, Any]:
        """Get all settings as dictionary."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM settings")
            settings = {row[0]: self._simple_parse(row[1]) for row in cursor.fetchall()}
        return settings

    def get_list(self, key: str, default: Optional[List[str]] = None) -> List[str]:
        """Get list configuration value from comma-separated string.

        Args:
            key: Setting key
            default: Default value if not found

        Returns:
            List of strings
        """
        value = self.get(key, default)
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            if value.strip():
                return [item.strip() for item in value.split(",") if item.strip()]
            return []
        if default is not None:
            return default
        return []

    def set_list(self, key: str, value: List[str]) -> None:
        """Set configuration value as comma-separated string.

        Args:
            key: Setting key
            value: List of strings to store
        """
        self.set(key, ",".join(str(v) for v in value))
