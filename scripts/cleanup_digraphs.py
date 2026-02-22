#!/usr/bin/env python3
"""Cleanup invalid digraphs from local and remote databases.

This script removes digraphs that don't appear in any valid German words from the dictionary.
It cleans both the local SQLite database and the remote PostgreSQL database.

Usage:
    python scripts/cleanup_digraphs.py --dry-run    # Preview what would be deleted
    python scripts/cleanup_digraphs.py --local-only # Only clean local database
    python scripts/cleanup_digraphs.py              # Clean both local and remote
"""

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlcipher3 as sqlite3

from core.dictionary import Dictionary
from core.dictionary_config import DictionaryConfig
from core.postgres_adapter import PostgreSQLAdapter
from utils.config import Config
from utils.crypto import CryptoManager

log = logging.getLogger("realtypecoach.cleanup_digraphs")


def get_valid_digraphs_from_dictionary(config: Config) -> set[str]:
    """Extract all valid digraphs from the German dictionary.

    Args:
        config: Application config

    Returns:
        Set of valid digraphs (e.g., {"ha", "au", "us", ...})
    """
    dict_config = DictionaryConfig(
        enabled_languages=["de"],
        auto_fallback=True,
        accept_all_mode=False,
        exclude_names_enabled=False,
    )

    dictionary = Dictionary(config=dict_config)

    if not dictionary.is_loaded():
        log.warning("Dictionary not loaded, accepting all digraphs")
        return set()

    valid_digraphs = set()

    # Extract digraphs from all words in the dictionary
    for lang_code, word_set in dictionary.words.items():
        log.info(f"Processing {len(word_set)} words from {lang_code} dictionary")

        for word in word_set:
            # Skip words shorter than 2 characters
            if len(word) < 2:
                continue

            # Extract all digraphs from this word
            for i in range(len(word) - 1):
                digraph = word[i:i+2]
                # Only include letter pairs (no special characters)
                if digraph.isalpha():
                    valid_digraphs.add(digraph.lower())

    log.info(f"Found {len(valid_digraphs)} unique valid digraphs in dictionary")
    return valid_digraphs


def get_local_digraphs(db_path: Path) -> list[dict]:
    """Get all digraphs from local SQLite database.

    Args:
        db_path: Path to local database

    Returns:
        List of dicts with digraph info
    """
    crypto = CryptoManager(db_path)
    key = crypto.get_key()

    if not key:
        log.error("No encryption key found in keyring")
        return []

    conn = sqlite3.connect(str(db_path))
    conn.execute(f"PRAGMA key = \"x'{key.hex()}'\"")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT first_key, second_key, total_sequences, avg_interval_ms
        FROM digraph_statistics
        ORDER BY avg_interval_ms DESC
    """)

    digraphs = []
    for row in cursor.fetchall():
        digraphs.append({
            "first_key": row[0],
            "second_key": row[1],
            "total_sequences": row[2],
            "avg_interval_ms": row[3],
        })

    conn.close()
    return digraphs


def get_remote_digraphs(adapter: PostgreSQLAdapter) -> list[dict]:
    """Get all digraphs from remote PostgreSQL database.

    Args:
        adapter: PostgreSQLAdapter instance

    Returns:
        List of dicts with digraph info
    """
    digraphs = []

    with adapter.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT first_key, second_key, total_sequences, avg_interval_ms
            FROM digraph_statistics
            ORDER BY avg_interval_ms DESC
        """)

        for row in cursor.fetchall():
            digraphs.append({
                "first_key": row[0],
                "second_key": row[1],
                "total_sequences": row[2],
                "avg_interval_ms": row[3],
            })

    return digraphs


def cleanup_local_digraphs(db_path: Path, invalid_digraphs: set[str], dry_run: bool) -> int:
    """Remove invalid digraphs from local database.

    Args:
        db_path: Path to local database
        invalid_digraphs: Set of invalid digraphs to remove
        dry_run: If True, don't actually delete

    Returns:
        Number of digraphs removed
    """
    crypto = CryptoManager(db_path)
    key = crypto.get_key()

    if not key:
        log.error("No encryption key found in keyring")
        return 0

    conn = sqlite3.connect(str(db_path))
    conn.execute(f"PRAGMA key = \"x'{key.hex()}'\"")
    cursor = conn.cursor()

    removed_count = 0

    for digraph in invalid_digraphs:
        first_key, second_key = digraph[0], digraph[1]

        if dry_run:
            cursor.execute("""
                SELECT COUNT(*) FROM digraph_statistics
                WHERE first_key = ? AND second_key = ?
            """, (first_key, second_key))
            count = cursor.fetchone()[0]
            if count > 0:
                log.info(f"Would delete: '{first_key}{second_key}' ({count} row(s))")
                removed_count += count
        else:
            cursor.execute("""
                DELETE FROM digraph_statistics
                WHERE first_key = ? AND second_key = ?
            """, (first_key, second_key))
            if cursor.rowcount > 0:
                log.info(f"Deleted: '{first_key}{second_key}' ({cursor.rowcount} row(s))")
                removed_count += cursor.rowcount

    if not dry_run:
        conn.commit()

    conn.close()
    return removed_count


def cleanup_remote_digraphs(adapter: PostgreSQLAdapter, invalid_digraphs: set[str], dry_run: bool) -> int:
    """Remove invalid digraphs from remote PostgreSQL database.

    Args:
        adapter: PostgresAdapter instance
        invalid_digraphs: Set of invalid digraphs to remove
        dry_run: If True, don't actually delete

    Returns:
        Number of digraphs removed
    """
    removed_count = 0

    with adapter.get_connection() as conn:
        cursor = conn.cursor()

        for digraph in invalid_digraphs:
            first_key, second_key = digraph[0], digraph[1]

            if dry_run:
                cursor.execute("""
                    SELECT COUNT(*) FROM digraph_statistics
                    WHERE first_key = %s AND second_key = %s
                """, (first_key, second_key))
                count = cursor.fetchone()[0]
                if count > 0:
                    log.info(f"[Remote] Would delete: '{first_key}{second_key}' ({count} row(s))")
                    removed_count += count
            else:
                cursor.execute("""
                    DELETE FROM digraph_statistics
                    WHERE first_key = %s AND second_key = %s
                """, (first_key, second_key))
                if cursor.rowcount > 0:
                    log.info(f"[Remote] Deleted: '{first_key}{second_key}' ({cursor.rowcount} row(s))")
                    removed_count += cursor.rowcount

        if not dry_run:
            conn.commit()

    return removed_count


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s"
    )

    parser = argparse.ArgumentParser(
        description="Cleanup invalid digraphs from database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --dry-run       # Preview what would be deleted
  %(prog)s --local-only    # Only clean local database
  %(prog)s                 # Clean both local and remote
        """,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without actually deleting"
    )
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Only clean local database, skip remote"
    )

    args = parser.parse_args()

    # Get database path
    db_path = Path.home() / ".local" / "share" / "realtypecoach" / "typing_data.db"

    # Load config
    config = Config(db_path)

    # Get valid digraphs from dictionary
    log.info("Loading dictionary to extract valid digraphs...")
    valid_digraphs = get_valid_digraphs_from_dictionary(config)

    if not valid_digraphs:
        log.error("No valid digraphs found in dictionary")
        sys.exit(1)

    # Get local digraphs
    if not db_path.exists():
        log.error(f"Database not found at {db_path}")
        sys.exit(1)

    log.info("Loading digraphs from local database...")
    local_digraphs = get_local_digraphs(db_path)
    log.info(f"Found {len(local_digraphs)} digraphs in local database")

    # Find invalid digraphs
    invalid_digraphs = set()
    for d in local_digraphs:
        digraph = f"{d['first_key']}{d['second_key']}".lower()
        if digraph not in valid_digraphs:
            invalid_digraphs.add(digraph)

    log.info(f"Found {len(invalid_digraphs)} invalid digraphs to remove")

    if len(invalid_digraphs) == 0:
        log.info("No invalid digraphs found in local database")
    else:
        # Show examples of invalid digraphs
        log.info("Examples of invalid digraphs:")
        for digraph in sorted(list(invalid_digraphs))[:20]:
            log.info(f"  - {digraph}")
        if len(invalid_digraphs) > 20:
            log.info(f"  ... and {len(invalid_digraphs) - 20} more")

    # Show examples of invalid digraphs
    log.info("Examples of invalid digraphs:")
    for digraph in sorted(list(invalid_digraphs))[:20]:
        log.info(f"  - {digraph}")
    if len(invalid_digraphs) > 20:
        log.info(f"  ... and {len(invalid_digraphs) - 20} more")

    if args.dry_run:
        log.info("\n=== DRY RUN MODE - No changes will be made ===")

    # Cleanup local database (if needed)
    if len(invalid_digraphs) > 0:
        log.info("\nCleaning local database...")
        local_removed = cleanup_local_digraphs(db_path, invalid_digraphs, args.dry_run)
        log.info(f"Local: {'Would remove' if args.dry_run else 'Removed'} {local_removed} digraph(s)")

    # Cleanup remote database (if not local-only)
    if not args.local_only:
        try:
            log.info("\nCleaning remote database...")

            # Get user_id from UserManager
            from core.user_manager import UserManager
            user_manager = UserManager(db_path, config)
            user = user_manager.get_or_create_current_user()

            # Get postgres password from keyring
            crypto = CryptoManager(db_path)
            postgres_password = crypto.get_postgres_password()

            if not postgres_password:
                log.error("PostgreSQL password not found in keyring")
                log.info("Please set up remote sync first or use --local-only")
            else:
                adapter = PostgreSQLAdapter(
                    host=config.get("postgres_host", ""),
                    port=config.get_int("postgres_port", 5432),
                    database=config.get("postgres_database", "realtypecoach"),
                    user=config.get("postgres_user", ""),
                    password=postgres_password,
                    sslmode=config.get("postgres_sslmode", "require"),
                    user_id=user.user_id,
                )
                adapter.initialize()

                # Get remote digraphs and find invalid ones
                log.info("Loading digraphs from remote database...")
                remote_digraphs = get_remote_digraphs(adapter)
                log.info(f"Found {len(remote_digraphs)} digraphs in remote database")

                # Find invalid remote digraphs
                remote_invalid = set()
                for d in remote_digraphs:
                    digraph = f"{d['first_key']}{d['second_key']}".lower()
                    if digraph not in valid_digraphs:
                        remote_invalid.add(digraph)

                log.info(f"Found {len(remote_invalid)} invalid digraphs to remove from remote")

                if len(remote_invalid) == 0:
                    log.info("Remote database is clean!")
                else:
                    # Show examples
                    log.info("Examples of invalid remote digraphs:")
                    for digraph in sorted(list(remote_invalid))[:20]:
                        log.info(f"  - {digraph}")
                    if len(remote_invalid) > 20:
                        log.info(f"  ... and {len(remote_invalid) - 20} more")

                    remote_removed = cleanup_remote_digraphs(adapter, remote_invalid, args.dry_run)
                    log.info(f"Remote: {'Would remove' if args.dry_run else 'Removed'} {remote_removed} digraph(s)")

        except Exception as e:
            log.error(f"Failed to clean remote database: {e}")
            log.info("You can run 'just sync' after fixing remote connection issues")

    if args.dry_run:
        log.info("\n=== DRY RUN COMPLETE - Run without --dry-run to apply changes ===")
    else:
        log.info("\n=== Cleanup complete! ===")


if __name__ == "__main__":
    main()
