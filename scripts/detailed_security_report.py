#!/usr/bin/env python3
"""Generate a detailed security report for the PostgreSQL server.

This script provides comprehensive information about the server's security configuration.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg2

from utils.config import Config
from utils.crypto import CryptoManager


def get_detailed_security_info():
    """Get detailed security information from the PostgreSQL server."""
    print("=" * 80)
    print("DETAILED POSTGRESQL SECURITY REPORT")
    print("=" * 80)

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

    # Connect to database
    try:
        conn = psycopg2.connect(
            host=config.get("postgres_host", ""),
            port=config.get_int("postgres_port", 5432),
            dbname=config.get("postgres_database", "realtypecoach"),
            user=config.get("postgres_user", ""),
            password=password,
            sslmode=config.get("postgres_sslmode", "require"),
        )

        cursor = conn.cursor()

        print("🔒 AUTHENTICATION SECURITY")
        print("-" * 80)

        # Password encryption
        cursor.execute("SHOW password_encryption;")
        password_encryption = cursor.fetchone()[0]
        print(f"Password encryption method: {password_encryption}")
        if password_encryption == "scram-sha-256":
            print("  ✓ SCRAM-SHA-256 is the most secure password encryption method")
        elif password_encryption == "md5":
            print("  ⚠ MD5 is considered weak - consider upgrading to SCRAM-SHA-256")

        # Authentication timeout
        cursor.execute("SHOW authentication_timeout;")
        auth_timeout = cursor.fetchone()[0]
        print(f"Authentication timeout: {auth_timeout} seconds")

        print("\n🔐 ENCRYPTION & SSL SECURITY")
        print("-" * 80)

        # SSL configuration
        cursor.execute("SHOW ssl;")
        ssl_enabled = cursor.fetchone()[0]
        print(f"SSL enabled: {ssl_enabled}")

        cursor.execute("SHOW ssl_cert_file;")
        ssl_cert = cursor.fetchone()[0]
        print(f"SSL certificate file: {ssl_cert}")

        cursor.execute("SHOW ssl_key_file;")
        ssl_key = cursor.fetchone()[0]
        print(f"SSL key file: {ssl_key}")

        # SSL cipher suites
        cursor.execute("SHOW ssl_ciphers;")
        ssl_ciphers = cursor.fetchone()[0]
        print(f"SSL cipher suites: {ssl_ciphers[:50]}...")

        print("\n📋 SERVER CONFIGURATION")
        print("-" * 80)

        # Server version
        cursor.execute("SHOW server_version;")
        version = cursor.fetchone()[0]
        print(f"PostgreSQL version: {version}")

        # Listen addresses
        cursor.execute("SHOW listen_addresses;")
        listen_addr = cursor.fetchone()[0]
        print(f"Listen addresses: {listen_addr}")

        # Port
        cursor.execute("SHOW port;")
        port = cursor.fetchone()[0]
        print(f"Port: {port}")

        print("\n🛡️ NETWORK SECURITY")
        print("-" * 80)

        # HBA file location
        cursor.execute("SHOW hba_file;")
        hba_file = cursor.fetchone()[0]
        print(f"HBA configuration file: {hba_file}")

        # TCP keepalives
        cursor.execute("SHOW tcp_keepalives_idle;")
        tcp_idle = cursor.fetchone()[0]
        print(f"TCP keepalives idle: {tcp_idle} seconds")

        cursor.execute("SHOW tcp_keepalives_interval;")
        tcp_interval = cursor.fetchone()[0]
        print(f"TCP keepalives interval: {tcp_interval} seconds")

        cursor.execute("SHOW tcp_keepalives_count;")
        tcp_count = cursor.fetchone()[0]
        print(f"TCP keepalives count: {tcp_count}")

        print("\n👤 USER & ROLE SECURITY")
        print("-" * 80)

        # List all roles
        cursor.execute("""
            SELECT rolname, rolsuper, rolinherit, rolcreaterole, rolcreatedb,
                   rolcanlogin, rolreplication, rolconnlimit, rolvaliduntil
            FROM pg_roles
            ORDER BY rolname
        """)
        roles = cursor.fetchall()

        print("Database roles and permissions:")
        for role in roles:
            (
                rolname,
                rolsuper,
                rolinherit,
                rolcreaterole,
                rolcreatedb,
                rolcanlogin,
                rolreplication,
                rolconnlimit,
                rolvaliduntil,
            ) = role
            print(f"  - {rolname}")
            print(
                f"    Superuser: {rolsuper}, Login: {rolcanlogin}, Connection limit: {rolconnlimit}"
            )
            if rolvaliduntil:
                print(f"    Valid until: {rolvaliduntil}")

        print("\n🔧 SECURITY BEST PRACTICES CHECK")
        print("-" * 80)

        # Check for security best practices
        security_checks = []

        # Check password encryption
        if password_encryption == "scram-sha-256":
            security_checks.append(("Password encryption", True, "SCRAM-SHA-256 is used"))
        else:
            security_checks.append(
                (
                    "Password encryption",
                    False,
                    f"Using {password_encryption} instead of SCRAM-SHA-256",
                )
            )

        # Check SSL
        if ssl_enabled == "on":
            security_checks.append(("SSL encryption", True, "SSL is enabled"))
        else:
            security_checks.append(("SSL encryption", False, "SSL is disabled"))

        # Check listen addresses
        if listen_addr == "localhost" or "*" not in listen_addr:
            security_checks.append(
                ("Network binding", True, f"Bound to {listen_addr} (restricted)")
            )
        else:
            security_checks.append(
                ("Network binding", False, f"Bound to {listen_addr} (may be too permissive)")
            )

        # Display security checks
        all_good = True
        for check_name, passed, details in security_checks:
            status = "✓" if passed else "⚠"
            print(f"{status} {check_name}: {details}")
            if not passed:
                all_good = False

        conn.close()

        print("\n" + "=" * 80)
        if all_good:
            print("✓ Server security configuration looks good!")
        else:
            print("⚠ Some security improvements are recommended")
        print("=" * 80)

        return True

    except Exception as e:
        print(f"✗ Error getting security information: {e}")
        return False


def main():
    """Main function."""
    success = get_detailed_security_info()
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
