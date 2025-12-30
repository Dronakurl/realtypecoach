"""Encryption key management using system keyring."""

import secrets
import logging
from pathlib import Path
from typing import Optional

try:
    import keyring
    from keyring.errors import KeyringError
except ImportError:
    keyring = None

log = logging.getLogger("realtypecoach.crypto")

# Keyring identifiers
APP_NAME = "realtypecoach"
KEY_SERVICE = "realtypecoach"
KEY_USERNAME = "database_encryption_key"

# Key specification
KEY_LENGTH = 32  # 256 bits for AES-256


class CryptoManager:
    """Manages encryption keys using system keyring."""

    def __init__(self, db_path: Path):
        """Initialize crypto manager.

        Args:
            db_path: Path to database file (used for validation)
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
        self._cached_key: Optional[bytes] = None

    def key_exists(self) -> bool:
        """Check if encryption key exists in keyring.

        Returns:
            True if key is stored
        """
        try:
            key = keyring.get_password(KEY_SERVICE, KEY_USERNAME)
            return key is not None
        except KeyringError as e:
            log.error(f"Error accessing keyring: {e}")
            return False

    def generate_key(self) -> bytes:
        """Generate a new random encryption key.

        Returns:
            32-byte key for AES-256
        """
        return secrets.token_bytes(KEY_LENGTH)

    def store_key(self, key: bytes) -> None:
        """Store encryption key in system keyring.

        Args:
            key: 32-byte encryption key

        Raises:
            RuntimeError: If keyring storage fails
        """
        if len(key) != KEY_LENGTH:
            raise ValueError(f"Key must be {KEY_LENGTH} bytes")

        # Encode key as hex for storage
        key_hex = key.hex()

        try:
            keyring.set_password(KEY_SERVICE, KEY_USERNAME, key_hex)
            log.info("Encryption key stored in system keyring")
            self._cached_key = key
        except KeyringError as e:
            raise RuntimeError(f"Failed to store key in keyring: {e}")

    def get_key(self) -> Optional[bytes]:
        """Retrieve encryption key from keyring.

        Returns:
            32-byte encryption key or None if not found
        """
        if self._cached_key:
            return self._cached_key

        try:
            key_hex = keyring.get_password(KEY_SERVICE, KEY_USERNAME)
            if key_hex:
                self._cached_key = bytes.fromhex(key_hex)
                return self._cached_key
        except KeyringError as e:
            log.error(f"Error retrieving key from keyring: {e}")

        return None

    def delete_key(self) -> None:
        """Delete encryption key from keyring."""
        try:
            keyring.delete_password(KEY_SERVICE, KEY_USERNAME)
            self._cached_key = None
            log.info("Encryption key removed from keyring")
        except KeyringError as e:
            log.error(f"Error deleting key from keyring: {e}")

    def initialize_database_key(self) -> bytes:
        """Initialize encryption for a new database.

        Generates a new key and stores it in the keyring.
        Should only be called when creating a fresh encrypted database.

        Returns:
            Generated encryption key

        Raises:
            RuntimeError: If key already exists or storage fails
        """
        if self.key_exists():
            raise RuntimeError(
                "Encryption key already exists. "
                "Cannot reinitialize without deleting existing key first."
            )

        key = self.generate_key()
        self.store_key(key)
        return key

    def get_or_create_key(self) -> bytes:
        """Get existing key or create new one if needed.

        Returns:
            Encryption key

        Raises:
            RuntimeError: If keyring operations fail
        """
        key = self.get_key()
        if key is None:
            log.info("No encryption key found, generating new key")
            key = self.initialize_database_key()
        return key
