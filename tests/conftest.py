"""Shared test fixtures for RealTypeCoach tests."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from utils.crypto import CryptoManager


class InMemoryKeyring:
    """Simple in-memory keyring for tests to avoid DBus issues."""

    def __init__(self):
        self._passwords: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self._passwords.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._passwords[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self._passwords.pop((service, username), None)


@pytest.fixture(autouse=True)
def mock_keyring():
    """Use in-memory keyring for all tests to avoid DBus race conditions."""
    mock = InMemoryKeyring()
    with patch("utils.crypto.keyring", mock):
        yield mock


@pytest.fixture
def temp_db_path():
    """Create a temporary database path and clean up afterwards."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        yield db_path


@pytest.fixture
def crypto_manager(temp_db_path):
    """Create a CryptoManager and ensure encryption key exists."""
    crypto = CryptoManager(temp_db_path)
    # Ensure key exists for tests
    if not crypto.key_exists():
        crypto.initialize_database_key()
    yield crypto
    # Clean up key after test
    try:
        crypto.delete_key()
    except Exception:
        pass
