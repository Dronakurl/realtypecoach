"""Encryption key management using system keyring."""

import hashlib
import logging
import secrets
from pathlib import Path

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
        self._cached_key: bytes | None = None

        # Migrate legacy key for existing databases
        self._migrate_legacy_key_if_needed()

    def _get_db_key_identifiers(self) -> tuple[str, str]:
        """Generate unique keyring identifiers for this database.

        Returns:
            Tuple of (service, username) for keyring operations
        """
        path_hash = hashlib.sha256(str(self.db_path.resolve()).encode()).hexdigest()[:16]
        return f"realtypecoach_{path_hash}", f"db_key_{path_hash}"

    def _get_legacy_key(self) -> bytes | None:
        """Get legacy hardcoded key if it exists.

        Returns:
            Legacy encryption key or None
        """
        try:
            key_hex = keyring.get_password(KEY_SERVICE, KEY_USERNAME)
            if key_hex:
                return bytes.fromhex(key_hex)
        except KeyringError:
            pass
        return None

    def _migrate_legacy_key_if_needed(self) -> None:
        """Migrate legacy hardcoded key to new path-based identifier."""
        # Check if we already have a path-specific key
        service, username = self._get_db_key_identifiers()
        try:
            if keyring.get_password(service, username) is not None:
                return  # Already have a path-specific key
        except KeyringError:
            pass

        # Try to get legacy key - only migrate if it exists
        legacy_key = self._get_legacy_key()
        if legacy_key:
            try:
                keyring.set_password(service, username, legacy_key.hex())
                self._cached_key = legacy_key
                log.info(f"Migrated legacy encryption key for {self.db_path}")
            except KeyringError as e:
                log.warning(f"Failed to migrate legacy key: {e}")

    def key_exists(self) -> bool:
        """Check if encryption key exists in keyring.

        Returns:
            True if key is stored
        """
        service, username = self._get_db_key_identifiers()
        try:
            key = keyring.get_password(service, username)
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
        service, username = self._get_db_key_identifiers()

        try:
            keyring.set_password(service, username, key_hex)
            log.info("Encryption key stored in system keyring")
            self._cached_key = key
        except KeyringError as e:
            raise RuntimeError(f"Failed to store key in keyring: {e}")

    def get_key(self) -> bytes | None:
        """Retrieve encryption key from keyring.

        Returns:
            32-byte encryption key or None if not found
        """
        if self._cached_key:
            return self._cached_key

        service, username = self._get_db_key_identifiers()
        try:
            key_hex = keyring.get_password(service, username)
            if key_hex:
                self._cached_key = bytes.fromhex(key_hex)
                return self._cached_key
        except KeyringError as e:
            log.error(f"Error retrieving key from keyring: {e}")

        return None

    def delete_key(self) -> None:
        """Delete encryption key from keyring."""
        service, username = self._get_db_key_identifiers()
        try:
            keyring.delete_password(service, username)
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

    def delete_legacy_key(self) -> None:
        """Delete the legacy hardcoded key from keyring.

        WARNING: Only call this after confirming migration succeeded.
        This is an optional cleanup operation.
        """
        try:
            keyring.delete_password(KEY_SERVICE, KEY_USERNAME)
            log.info("Legacy encryption key removed from keyring")
        except KeyringError as e:
            log.error(f"Error deleting legacy key: {e}")

    # ========== PostgreSQL Password Storage ==========

    POSTGRES_SERVICE = "realtypecoach_postgres"
    POSTGRES_USERNAME = "database_user"

    def store_postgres_password(self, password: str) -> None:
        """Store PostgreSQL password in keyring.

        Args:
            password: PostgreSQL password

        Raises:
            RuntimeError: If keyring storage fails
        """
        if not password:
            raise ValueError("Password cannot be empty")

        try:
            keyring.set_password(self.POSTGRES_SERVICE, self.POSTGRES_USERNAME, password)
            log.info("PostgreSQL password stored in system keyring")
        except KeyringError as e:
            raise RuntimeError(f"Failed to store PostgreSQL password in keyring: {e}")

    def get_postgres_password(self) -> str | None:
        """Retrieve PostgreSQL password from keyring.

        Returns:
            PostgreSQL password or None if not found
        """
        try:
            password = keyring.get_password(self.POSTGRES_SERVICE, self.POSTGRES_USERNAME)
            return password
        except KeyringError as e:
            log.error(f"Error retrieving PostgreSQL password from keyring: {e}")
            return None

    def delete_postgres_password(self) -> None:
        """Delete PostgreSQL password from keyring."""
        try:
            keyring.delete_password(self.POSTGRES_SERVICE, self.POSTGRES_USERNAME)
            log.info("PostgreSQL password removed from keyring")
        except KeyringError as e:
            log.error(f"Error deleting PostgreSQL password: {e}")

    # ========== User Encryption Key Storage ==========

    USER_KEY_SERVICE_PREFIX = "realtypecoach_user"
    USER_KEY_USERNAME = "encryption_key"

    def store_user_encryption_key(self, user_id: str, key: bytes) -> None:
        """Store user encryption key in keyring.

        Args:
            user_id: User UUID
            key: 32-byte encryption key

        Raises:
            RuntimeError: If keyring storage fails
        """
        if len(key) != 32:
            raise ValueError(f"Key must be 32 bytes, got {len(key)}")

        # Encode key as hex for storage
        key_hex = key.hex()
        service = f"{self.USER_KEY_SERVICE_PREFIX}_{user_id}"

        try:
            keyring.set_password(service, self.USER_KEY_USERNAME, key_hex)
            log.info(f"User encryption key stored for {user_id}")
        except KeyringError as e:
            raise RuntimeError(f"Failed to store user key in keyring: {e}")

    def get_user_encryption_key(self, user_id: str) -> bytes | None:
        """Retrieve user encryption key from keyring.

        Args:
            user_id: User UUID

        Returns:
            32-byte encryption key or None if not found
        """
        service = f"{self.USER_KEY_SERVICE_PREFIX}_{user_id}"
        try:
            key_hex = keyring.get_password(service, self.USER_KEY_USERNAME)
            if key_hex:
                return bytes.fromhex(key_hex)
        except KeyringError as e:
            log.error(f"Error retrieving user key from keyring: {e}")
        return None

    def delete_user_encryption_key(self, user_id: str) -> None:
        """Delete user encryption key from keyring.

        Args:
            user_id: User UUID
        """
        service = f"{self.USER_KEY_SERVICE_PREFIX}_{user_id}"
        try:
            keyring.delete_password(service, self.USER_KEY_USERNAME)
            log.info(f"User encryption key removed for {user_id}")
        except KeyringError as e:
            log.error(f"Error deleting user key: {e}")
