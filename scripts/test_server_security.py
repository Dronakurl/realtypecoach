#!/usr/bin/env python3
"""Test server security configuration for PostgreSQL.

This script checks:
1. If password authentication is required
2. If password encryption is enabled
3. If SSL/TLS is configured
4. If the server is accessible without credentials
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg2

from utils.config import Config
from utils.crypto import CryptoManager


def test_connection_with_credentials():
    """Test connection with proper credentials."""
    print("=" * 70)
    print("Testing connection with credentials...")
    print("=" * 70)

    # Get database path for config
    db_path = Path.home() / ".local" / "share" / "realtypecoach" / "typing_data.db"

    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        return False

    # Load config
    try:
        config = Config(db_path)
    except Exception as e:
        print(f"Error loading config: {e}")
        return False

    if not config.get_bool("postgres_sync_enabled", False):
        print("PostgreSQL sync is not enabled in config")
        return False

    # Get PostgreSQL password
    try:
        crypto = CryptoManager(db_path)
        password = crypto.get_postgres_password()
        if not password:
            print("Error: PostgreSQL password not found")
            return False
    except Exception as e:
        print(f"Error getting PostgreSQL password: {e}")
        return False

    # Test connection
    try:
        conn = psycopg2.connect(
            host=config.get("postgres_host", ""),
            port=config.get_int("postgres_port", 5432),
            dbname=config.get("postgres_database", "realtypecoach"),
            user=config.get("postgres_user", ""),
            password=password,
            sslmode=config.get("postgres_sslmode", "require"),
        )

        # Get server version and settings
        cursor = conn.cursor()

        # Check server version
        cursor.execute("SHOW server_version;")
        version = cursor.fetchone()[0]
        print(f"✓ Connected to PostgreSQL: {version}")

        # Check password encryption setting
        cursor.execute("SHOW password_encryption;")
        password_encryption = cursor.fetchone()[0]
        print(f"✓ Password encryption: {password_encryption}")

        # Check SSL setting
        cursor.execute("SHOW ssl;")
        ssl_enabled = cursor.fetchone()[0]
        print(f"✓ SSL enabled: {ssl_enabled}")

        # Check authentication methods
        cursor.execute("""
            SELECT name, setting FROM pg_settings
            WHERE name IN ('password_encryption', 'ssl', 'hba_file')
        """)
        settings = cursor.fetchall()
        for name, setting in settings:
            print(f"  - {name}: {setting}")

        conn.close()
        return True

    except Exception as e:
        print(f"✗ Error connecting with credentials: {e}")
        return False


def test_connection_without_credentials():
    """Test if server is accessible without credentials (security vulnerability)."""
    print("\n" + "=" * 70)
    print("Testing connection WITHOUT credentials (security check)...")
    print("=" * 70)

    # Get database path for config
    db_path = Path.home() / ".local" / "share" / "realtypecoach" / "typing_data.db"

    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        return False

    # Load config
    try:
        config = Config(db_path)
    except Exception as e:
        print(f"Error loading config: {e}")
        return False

    if not config.get_bool("postgres_sync_enabled", False):
        print("PostgreSQL sync is not enabled in config")
        return False

    # Try to connect without password
    try:
        conn = psycopg2.connect(
            host=config.get("postgres_host", ""),
            port=config.get_int("postgres_port", 5432),
            dbname=config.get("postgres_database", "realtypecoach"),
            user=config.get("postgres_user", ""),
            # No password provided
            sslmode=config.get("postgres_sslmode", "require"),
        )

        print("✗ SECURITY ISSUE: Server is accessible without password!")
        conn.close()
        return False

    except psycopg2.OperationalError as e:
        error_str = str(e)
        if "password authentication failed" in error_str or "no password supplied" in error_str:
            print("✓ Good: Server requires password authentication")
            return True
        else:
            print(f"✗ Connection error (may not be security-related): {e}")
            return False
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False


def test_ssl_configuration():
    """Test SSL configuration."""
    print("\n" + "=" * 70)
    print("Testing SSL configuration...")
    print("=" * 70)

    # Get database path for config
    db_path = Path.home() / ".local" / "share" / "realtypecoach" / "typing_data.db"

    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        return False

    # Load config
    try:
        config = Config(db_path)
    except Exception as e:
        print(f"Error loading config: {e}")
        return False

    sslmode = config.get("postgres_sslmode", "require")
    print(f"✓ SSL mode configured: {sslmode}")

    if sslmode in ["require", "verify-ca", "verify-full"]:
        print("✓ Good: SSL is required for connections")
        return True
    else:
        print(f"⚠ Warning: SSL mode is '{sslmode}' - connections may not be encrypted")
        return False


def main():
    """Main function to run all security tests."""
    print("PostgreSQL Server Security Test")
    print("=" * 70)

    results = []

    # Test 1: Connection with credentials
    results.append(("Credentials test", test_connection_with_credentials()))

    # Test 2: Connection without credentials (should fail)
    results.append(("No-credentials test", test_connection_without_credentials()))

    # Test 3: SSL configuration
    results.append(("SSL configuration", test_ssl_configuration()))

    # Summary
    print("\n" + "=" * 70)
    print("SECURITY TEST SUMMARY")
    print("=" * 70)

    all_passed = True
    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {test_name}")
        if not passed:
            all_passed = False

    print("=" * 70)
    if all_passed:
        print("✓ All security tests passed!")
    else:
        print("✗ Some security tests failed - review server configuration")

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
