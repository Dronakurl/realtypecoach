"""User identity and encryption key management.

Manages user identity and encryption keys for multi-user PostgreSQL sync.
Auto-generates unique user_id (UUID) and username on first launch.
Generates unique AES-256 encryption key per user.
Stores encryption key in system keyring.
Supports export/import of encryption key for multi-device setup.
"""

import base64
import logging
import os
import platform
import secrets
import socket
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

try:
    import keyring
    from keyring.errors import KeyringError
except ImportError:
    keyring = None

log = logging.getLogger("realtypecoach.user_manager")

# Keyring identifiers for user encryption keys
USER_KEY_SERVICE_PREFIX = "realtypecoach_user"
USER_KEY_USERNAME = "encryption_key"

# Key specification
KEY_LENGTH = 32  # 256 bits for AES-256


@dataclass
class User:
    """User identity information."""

    user_id: str  # UUID as string
    username: str  # Human-readable username (e.g., "desktop_abc123")
    email: str | None = None
    display_name: str | None = None
    created_at: int | None = None  # Milliseconds since epoch
    last_sync: int | None = None  # Milliseconds since epoch
    is_active: bool = True
    metadata: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
            "display_name": self.display_name,
            "created_at": self.created_at,
            "last_sync": self.last_sync,
            "is_active": self.is_active,
            "metadata": self.metadata,
        }


class UserManager:
    """Manage user identity and encryption keys.

    Key functionality:
    - Auto-generate unique user_id (UUID) and username on first launch
    - Generate unique AES-256 encryption key per user
    - Store encryption key in system keyring
    - Retrieve current user identity
    - Export/import encryption key for multi-device setup
    - Validate user_id from key (user_id encoded in key or stored separately)
    """

    def __init__(self, db_path: Path, config: "Config"):
        """Initialize user manager.

        Args:
            db_path: Path to database file (for config storage)
            config: Config instance for accessing settings

        Raises:
            RuntimeError: If keyring is not available
        """
        if keyring is None:
            raise RuntimeError(
                "System keyring is not available.\n\n"
                "RealTypeCoach requires a keyring to encrypt your typing data securely.\n\n"
                "For Ubuntu/Debian: sudo apt-get install python3-keyring gnome-keyring\n"
                "For Fedora: sudo dnf install python3-keyring keyring\n"
                "For Arch: sudo pacman -S python-keyring\n\n"
                "Or install with pip: pip install keyring"
            )

        self.db_path = db_path
        self.config = config
        self._cached_user: User | None = None

    def get_or_create_current_user(self) -> User:
        """Get current user or create new user if none exists.

        Returns:
            Current user

        Raises:
            RuntimeError: If user creation or key storage fails
        """
        if self._cached_user:
            return self._cached_user

        # Check if user exists in config
        user_id = self.config.get("current_user_id", "")
        username = self.config.get("current_username", "")
        email = self.config.get("current_user_email", None)

        if user_id and username:
            # User exists, load their encryption key
            user = User(
                user_id=user_id,
                username=username,
                email=email,
                display_name=self.config.get("current_user_display_name", None),
                created_at=self.config.get_int("current_user_created_at"),
                last_sync=self.config.get_int("last_sync_timestamp"),
                is_active=self.config.get_bool("current_user_is_active", True),
                metadata=self.config.get("current_user_metadata", None),
            )

            # Verify encryption key exists
            if not self._has_encryption_key(user_id):
                log.warning(f"Encryption key not found for user {user_id}, creating new key")
                self._create_and_store_user_encryption_key(user_id)

            self._cached_user = user
            return user

        # No user exists, create new user
        log.info("No user found, creating new user")
        user = self._create_new_user()
        self._cached_user = user
        return user

    def _create_new_user(self) -> User:
        """Create a new user with unique ID and encryption key.

        Returns:
            Newly created user

        Raises:
            RuntimeError: If user creation or key storage fails
        """
        # Generate unique user_id (UUID)
        user_id = str(uuid.uuid4())

        # Generate unique username (hostname + random suffix)
        hostname = self._get_hostname()
        random_suffix = secrets.token_hex(3)
        username = f"{hostname}_{random_suffix}"

        # Create user object
        now_ms = int(time.time() * 1000)
        user = User(
            user_id=user_id,
            username=username,
            email=None,
            display_name=None,
            created_at=now_ms,
            last_sync=None,
            is_active=True,
            metadata=None,
        )

        # Generate and store encryption key
        self._create_and_store_user_encryption_key(user_id)

        # Save user to config
        self.config.set("current_user_id", user_id)
        self.config.set("current_username", username)
        self.config.set("current_user_email", "")
        self.config.set("current_user_display_name", "")
        self.config.set("current_user_created_at", str(now_ms))
        self.config.set("current_user_is_active", "True")
        self.config.set("current_user_metadata", "")

        log.info(f"Created new user: {username} ({user_id})")
        return user

    def _get_hostname(self) -> str:
        """Get current hostname for username generation.

        Returns:
            Hostname (lowercase, alphanumeric only)
        """
        try:
            hostname = socket.gethostname()
            # Clean up hostname: lowercase, alphanumeric only
            hostname = "".join(c.lower() if c.isalnum() else "_" for c in hostname)
            # Truncate to reasonable length
            return hostname[:20]
        except Exception:
            return "device"

    def _create_and_store_user_encryption_key(self, user_id: str) -> bytes:
        """Generate and store encryption key for user.

        Args:
            user_id: User UUID

        Returns:
            Generated encryption key

        Raises:
            RuntimeError: If key storage fails
        """
        key = secrets.token_bytes(KEY_LENGTH)
        self._store_user_encryption_key(user_id, key)
        return key

    def _store_user_encryption_key(self, user_id: str, key: bytes) -> None:
        """Store encryption key in keyring.

        Args:
            user_id: User UUID
            key: 32-byte encryption key

        Raises:
            RuntimeError: If keyring storage fails
        """
        if len(key) != KEY_LENGTH:
            raise ValueError(f"Key must be {KEY_LENGTH} bytes")

        # Encode key as hex for storage
        key_hex = key.hex()
        service = f"{USER_KEY_SERVICE_PREFIX}_{user_id}"

        try:
            keyring.set_password(service, USER_KEY_USERNAME, key_hex)
            log.info(f"Encryption key stored for user {user_id}")
        except KeyringError as e:
            raise RuntimeError(f"Failed to store key in keyring: {e}")

    def _get_user_encryption_key(self, user_id: str) -> bytes | None:
        """Get encryption key from keyring.

        Args:
            user_id: User UUID

        Returns:
            32-byte encryption key or None if not found
        """
        service = f"{USER_KEY_SERVICE_PREFIX}_{user_id}"
        try:
            key_hex = keyring.get_password(service, USER_KEY_USERNAME)
            if key_hex:
                return bytes.fromhex(key_hex)
        except KeyringError as e:
            log.error(f"Error retrieving key from keyring: {e}")
        return None

    def _has_encryption_key(self, user_id: str) -> bool:
        """Check if encryption key exists in keyring.

        Args:
            user_id: User UUID

        Returns:
            True if key exists
        """
        return self._get_user_encryption_key(user_id) is not None

    def get_encryption_key(self, user_id: str | None = None) -> bytes:
        """Get encryption key for user.

        Args:
            user_id: User UUID (uses current user if None)

        Returns:
            32-byte encryption key

        Raises:
            RuntimeError: If key not found
        """
        if user_id is None:
            user = self.get_or_create_current_user()
            user_id = user.user_id

        key = self._get_user_encryption_key(user_id)
        if key is None:
            raise RuntimeError(f"Encryption key not found for user {user_id}")
        return key

    def update_username(self, username: str) -> None:
        """Update username for current user.

        Args:
            username: New username
        """
        user = self.get_or_create_current_user()

        # Validate username (alphanumeric, underscore, hyphen only)
        clean_username = "".join(c if c.isalnum() or c in "_-" else "_" for c in username)
        clean_username = clean_username[:50]  # Max length

        if not clean_username:
            raise ValueError("Username cannot be empty after validation")

        # Update config
        self.config.set("current_username", clean_username)

        # Update cached user
        self._cached_user = User(
            user_id=user.user_id,
            username=clean_username,
            email=user.email,
            display_name=user.display_name,
            created_at=user.created_at,
            last_sync=user.last_sync,
            is_active=user.is_active,
            metadata=user.metadata,
        )

        log.info(f"Updated username to: {clean_username}")

    def export_encryption_key(self) -> str:
        """Export encryption key for multi-device setup.

        Returns:
            Base64 encoded string containing user_id:key
            Format: base64(user_id:32bytes_key)

        Raises:
            RuntimeError: If no user exists or key not found
        """
        user = self.get_or_create_current_user()
        key = self.get_encryption_key(user.user_id)

        # Format: user_id:32bytes_key
        key_data = f"{user.user_id}:{key.hex()}"
        return base64.b64encode(key_data.encode()).decode()

    def import_encryption_key(self, key_data: str) -> User:
        """Import encryption key from another device.

        Args:
            key_data: Base64 encoded key from export_encryption_key()

        Returns:
            Imported user

        Raises:
            ValueError: If key is invalid
            RuntimeError: If key storage fails
        """
        try:
            # Decode base64
            decoded = base64.b64decode(key_data).decode()
            user_id, key_hex = decoded.split(":")

            # Validate UUID format
            uuid.UUID(user_id)

            # Validate and convert key
            key = bytes.fromhex(key_hex)
            if len(key) != KEY_LENGTH:
                raise ValueError(f"Invalid key length: {len(key)} bytes, expected {KEY_LENGTH}")

            # Store key
            self._store_user_encryption_key(user_id, key)

            # Extract username from user_id or generate new one
            hostname = self._get_hostname()
            random_suffix = secrets.token_hex(3)
            username = f"{hostname}_{random_suffix}"

            # Update config with imported user
            now_ms = int(time.time() * 1000)
            self.config.set("current_user_id", user_id)
            self.config.set("current_username", username)
            self.config.set("current_user_email", "")
            self.config.set("current_user_display_name", "")
            self.config.set("current_user_created_at", str(now_ms))
            self.config.set("current_user_is_active", "True")
            self.config.set("current_user_metadata", "")

            # Clear cached user to force reload
            self._cached_user = None

            user = self.get_or_create_current_user()
            log.info(f"Imported encryption key for user: {user_id}")
            return user

        except (ValueError, base64.binascii.Error) as e:
            raise ValueError(f"Invalid encryption key format: {e}")

    def has_encryption_key(self) -> bool:
        """Check if current user has an encryption key.

        Returns:
            True if encryption key exists
        """
        try:
            user = self.get_or_create_current_user()
            return self._has_encryption_key(user.user_id)
        except RuntimeError:
            return False

    def update_last_sync(self, timestamp_ms: int | None = None) -> None:
        """Update last sync timestamp.

        Args:
            timestamp_ms: Timestamp in milliseconds (uses current time if None)
        """
        if timestamp_ms is None:
            timestamp_ms = int(time.time() * 1000)

        self.config.set("last_sync_timestamp", str(timestamp_ms))

        # Update cached user
        if self._cached_user:
            self._cached_user.last_sync = timestamp_ms

    def get_last_sync(self) -> int | None:
        """Get last sync timestamp.

        Returns:
            Last sync timestamp in milliseconds or None
        """
        return self.config.get_int("last_sync_timestamp")

    def delete_user_encryption_key(self, user_id: str | None = None) -> None:
        """Delete encryption key from keyring.

        WARNING: This will make PostgreSQL data inaccessible!

        Args:
            user_id: User UUID (uses current user if None)
        """
        if user_id is None:
            user = self.get_or_create_current_user()
            user_id = user.user_id

        service = f"{USER_KEY_SERVICE_PREFIX}_{user_id}"
        try:
            keyring.delete_password(service, USER_KEY_USERNAME)
            log.info(f"Deleted encryption key for user {user_id}")
        except KeyringError as e:
            log.error(f"Error deleting key: {e}")
