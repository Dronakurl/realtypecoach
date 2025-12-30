"""Shared test fixtures for RealTypeCoach tests."""

import pytest
import tempfile
from pathlib import Path

from utils.crypto import CryptoManager


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
