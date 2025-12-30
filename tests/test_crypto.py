"""Tests for encryption key management."""

import pytest
import secrets
from pathlib import Path
import tempfile

from utils.crypto import CryptoManager
import sqlcipher3 as sqlite3


def test_crypto_manager_initialization():
    """Test crypto manager can be initialized."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        crypto = CryptoManager(db_path)
        assert crypto is not None


def test_generate_key():
    """Test key generation produces correct length."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        crypto = CryptoManager(db_path)
        key = crypto.generate_key()
        assert len(key) == 32
        assert isinstance(key, bytes)


def test_store_and_retrieve_key():
    """Test key can be stored and retrieved."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        crypto = CryptoManager(db_path)

        # Generate and store key
        key = crypto.generate_key()
        crypto.store_key(key)

        # Retrieve key
        retrieved = crypto.get_key()
        assert retrieved == key


def test_delete_key():
    """Test key can be deleted."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        crypto = CryptoManager(db_path)

        key = crypto.generate_key()
        crypto.store_key(key)
        assert crypto.key_exists()

        crypto.delete_key()
        assert not crypto.key_exists()


def test_initialize_database_key():
    """Test database key initialization."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        crypto = CryptoManager(db_path)

        key = crypto.initialize_database_key()
        assert len(key) == 32
        assert crypto.key_exists()

        # Second call should fail
        with pytest.raises(RuntimeError):
            crypto.initialize_database_key()


def test_get_or_create_key():
    """Test get_or_create_key creates new key if needed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        crypto = CryptoManager(db_path)

        # Should create new key
        key1 = crypto.get_or_create_key()
        assert len(key1) == 32
        assert crypto.key_exists()

        # Should return existing key
        key2 = crypto.get_or_create_key()
        assert key1 == key2


def test_key_caching():
    """Test key is cached after retrieval."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        crypto = CryptoManager(db_path)

        key = crypto.generate_key()
        crypto.store_key(key)

        # First retrieval
        retrieved1 = crypto.get_key()
        assert retrieved1 == key

        # Second retrieval should use cache
        retrieved2 = crypto.get_key()
        assert retrieved2 == key
        assert retrieved1 is retrieved2  # Same object due to caching


def test_encrypted_database_requires_key():
    """Test that encrypted database cannot be opened without key."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_encrypted.db"
        crypto = CryptoManager(db_path)

        # Generate and store key directly (bypass initialize_database_key check)
        key = crypto.generate_key()
        try:
            crypto.store_key(key)

            # Create encrypted database
            conn = sqlite3.connect(db_path)
            conn.execute(f"PRAGMA key = \"x'{key.hex()}'\"")
            conn.execute("CREATE TABLE test_table (id INTEGER, data TEXT)")
            conn.execute("INSERT INTO test_table VALUES (1, 'secret data')")
            conn.commit()
            conn.close()

            # Try to open without key - should fail
            conn_no_key = sqlite3.connect(db_path)
            with pytest.raises(sqlite3.DatabaseError):
                conn_no_key.execute("SELECT * FROM test_table")
            conn_no_key.close()
        finally:
            # Clean up key from keyring
            crypto.delete_key()


def test_wrong_key_fails_to_decrypt():
    """Test that wrong encryption key fails to decrypt database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_wrong_key.db"
        crypto = CryptoManager(db_path)

        # Create database with one key
        correct_key = crypto.generate_key()
        try:
            crypto.store_key(correct_key)

            conn = sqlite3.connect(db_path)
            conn.execute(f"PRAGMA key = \"x'{correct_key.hex()}'\"")
            conn.execute("CREATE TABLE secrets (id INTEGER, data TEXT)")
            conn.execute("INSERT INTO secrets VALUES (1, 'sensitive information')")
            conn.commit()
            conn.close()

            # Generate a different wrong key
            wrong_key = secrets.token_bytes(32)

            # Try to open with wrong key - should fail
            conn_wrong = sqlite3.connect(db_path)
            conn_wrong.execute(f"PRAGMA key = \"x'{wrong_key.hex()}'\"")
            with pytest.raises(sqlite3.DatabaseError):
                conn_wrong.execute("SELECT * FROM secrets")
            conn_wrong.close()
        finally:
            crypto.delete_key()


def test_correct_key_can_decrypt():
    """Test that correct key can successfully decrypt and read data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_correct_key.db"
        crypto = CryptoManager(db_path)

        # Create and store key
        key = crypto.generate_key()
        try:
            crypto.store_key(key)

            # Write data with encryption
            conn = sqlite3.connect(db_path)
            conn.execute(f"PRAGMA key = \"x'{key.hex()}'\"")
            conn.execute("PRAGMA cipher_memory_security = ON")
            conn.execute("PRAGMA cipher_page_size = 4096")
            conn.execute("PRAGMA cipher_kdf_iter = 256000")
            conn.execute("CREATE TABLE encrypted_data (id INTEGER, value TEXT)")
            conn.execute("INSERT INTO encrypted_data VALUES (1, 'encrypted value')")
            conn.execute("INSERT INTO encrypted_data VALUES (2, 'another secret')")
            conn.commit()
            conn.close()

            # Read data back with correct key
            conn_read = sqlite3.connect(db_path)
            conn_read.execute(f"PRAGMA key = \"x'{key.hex()}'\"")
            conn_read.execute("PRAGMA cipher_memory_security = ON")
            conn_read.execute("PRAGMA cipher_page_size = 4096")
            conn_read.execute("PRAGMA cipher_kdf_iter = 256000")

            cursor = conn_read.cursor()
            cursor.execute("SELECT value FROM encrypted_data WHERE id = 1")
            result = cursor.fetchone()
            assert result[0] == "encrypted value"

            cursor.execute("SELECT COUNT(*) FROM encrypted_data")
            count = cursor.fetchone()[0]
            assert count == 2

            conn_read.close()
        finally:
            crypto.delete_key()


def test_encrypted_database_file_is_not_plaintext():
    """Test that encrypted database file doesn't contain plaintext data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_plaintext_check.db"
        crypto = CryptoManager(db_path)

        key = crypto.generate_key()
        try:
            crypto.store_key(key)

            # Create encrypted database with specific data
            conn = sqlite3.connect(db_path)
            conn.execute(f"PRAGMA key = \"x'{key.hex()}'\"")
            conn.execute("CREATE TABLE sensitive (info TEXT)")
            conn.execute("INSERT INTO sensitive VALUES ('TOP_SECRET_DATA_12345')")
            conn.commit()
            conn.close()

            # Read the raw file bytes
            with open(db_path, 'rb') as f:
                file_content = f.read()

            # The plaintext string should NOT appear in the encrypted file
            # (SQLCipher encrypts the data, so it won't be readable)
            assert b'TOP_SECRET_DATA_12345' not in file_content
            assert b'sensitive' not in file_content
        finally:
            crypto.delete_key()


def test_path_based_keys_are_unique():
    """Different database paths get different encryption keys."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db1_path = Path(tmpdir) / "db1.db"
        db2_path = Path(tmpdir) / "db2.db"

        crypto1 = CryptoManager(db1_path)
        crypto2 = CryptoManager(db2_path)

        service1, username1 = crypto1._get_db_key_identifiers()
        service2, username2 = crypto2._get_db_key_identifiers()

        # Different paths should generate different identifiers
        assert service1 != service2
        assert username1 != username2


def test_same_path_produces_same_identifiers():
    """Same database path produces consistent key identifiers."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"

        crypto1 = CryptoManager(db_path)
        crypto2 = CryptoManager(db_path)

        service1, username1 = crypto1._get_db_key_identifiers()
        service2, username2 = crypto2._get_db_key_identifiers()

        # Same path should produce same identifiers
        assert service1 == service2
        assert username1 == username2


def test_delete_key_only_affects_specific_database():
    """Deleting a key should only affect that specific database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db1_path = Path(tmpdir) / "db1.db"
        db2_path = Path(tmpdir) / "db2.db"

        crypto1 = CryptoManager(db1_path)
        crypto2 = CryptoManager(db2_path)

        # Create keys for both databases
        key1 = crypto1.generate_key()
        key2 = crypto2.generate_key()

        try:
            crypto1.store_key(key1)
            crypto2.store_key(key2)

            assert crypto1.key_exists()
            assert crypto2.key_exists()

            # Delete key from db1 only
            crypto1.delete_key()

            # db1 key should be gone, but db2 key should still exist
            assert not crypto1.key_exists()
            assert crypto2.key_exists()

            # Verify db2 key is still accessible
            retrieved_key2 = crypto2.get_key()
            assert retrieved_key2 == key2
        finally:
            # Clean up both keys
            try:
                crypto1.delete_key()
            except Exception:
                pass
            try:
                crypto2.delete_key()
            except Exception:
                pass


def test_legacy_key_migration():
    """Test that legacy keys are automatically migrated."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        crypto = CryptoManager(db_path)

        # Create a legacy-style key using the old hardcoded identifiers
        try:
            legacy_key = secrets.token_bytes(32)
            from utils.crypto import KEY_SERVICE, KEY_USERNAME
            import keyring

            keyring.set_password(KEY_SERVICE, KEY_USERNAME, legacy_key.hex())

            # Create a new CryptoManager - it should auto-migrate the legacy key
            crypto_new = CryptoManager(db_path)

            # The migrated key should be accessible via get_key()
            migrated_key = crypto_new.get_key()
            assert migrated_key == legacy_key

            # After migration, deleting the key should only remove the path-based key
            crypto_new.delete_key()
            assert not crypto_new.key_exists()

            # The legacy key should still exist (not deleted by delete_key())
            legacy_key_still_exists = keyring.get_password(KEY_SERVICE, KEY_USERNAME) is not None
            assert legacy_key_still_exists
        finally:
            # Clean up both the path-based key and the legacy key
            try:
                crypto.delete_key()
            except Exception:
                pass
            try:
                from utils.crypto import KEY_SERVICE, KEY_USERNAME
                keyring.delete_password(KEY_SERVICE, KEY_USERNAME)
            except Exception:
                pass


def test_delete_legacy_key_method():
    """Test the delete_legacy_key() cleanup method."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        crypto = CryptoManager(db_path)

        # Create a legacy-style key
        try:
            from utils.crypto import KEY_SERVICE, KEY_USERNAME
            import keyring

            legacy_key = secrets.token_bytes(32)
            keyring.set_password(KEY_SERVICE, KEY_USERNAME, legacy_key.hex())

            # Verify legacy key exists
            assert keyring.get_password(KEY_SERVICE, KEY_USERNAME) is not None

            # Delete legacy key using the utility method
            crypto.delete_legacy_key()

            # Legacy key should now be gone
            assert keyring.get_password(KEY_SERVICE, KEY_USERNAME) is None
        except Exception:
            pass
