#!/usr/bin/env python3
"""Get quick statistics from local SQLite database.

Usage:
    python scripts/local_stats.py
    python scripts/local_stats.py --user-id <uuid>
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import sqlcipher3 as sqlite3

from utils.crypto import CryptoManager


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Get encrypted SQLite connection."""
    crypto = CryptoManager(db_path)
    encryption_key = crypto.get_key()
    if encryption_key is None:
        raise RuntimeError(
            "Database encryption key not found in keyring. "
            "This may indicate a corrupted installation or data migration issue."
        )

    # Connect with SQLCipher
    conn = sqlite3.connect(str(db_path))

    # Set encryption key (must be done IMMEDIATELY after connection)
    conn.execute(f"PRAGMA key = \"x'{encryption_key.hex()}'\"")

    # Verify database is accessible
    try:
        conn.execute("SELECT count(*) FROM sqlite_master")
    except sqlite3.DatabaseError as e:
        conn.close()
        raise RuntimeError(
            f"Cannot decrypt database. Wrong encryption key or corrupted database. Error: {e}"
        )

    # Set encryption parameters
    conn.execute("PRAGMA cipher_memory_security = ON")
    conn.execute("PRAGMA cipher_page_size = 4096")
    conn.execute("PRAGMA cipher_kdf_iter = 256000")

    return conn


def get_stats(db_path: Path, user_id: str | None = None):
    """Get statistics from local database."""
    conn = get_connection(db_path)

    print("=" * 70)
    print("Local SQLite Database Statistics")
    print("=" * 70)

    # Check if there's a user_id column in bursts
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(bursts)")
    columns = {row[1] for row in cursor.fetchall()}

    if "user_id" in columns:
        # Multi-user schema
        cursor.execute("SELECT DISTINCT user_id FROM bursts ORDER BY user_id")
        all_users = [row[0] for row in cursor.fetchall()]

        if user_id:
            print(f"👤 User: {user_id[:8]}...")
            print()
            _show_user_stats(cursor, user_id)
        else:
            for uid in all_users:
                print(f"👤 User: {uid[:8]}...")
                _show_user_stats(cursor, uid)
                print()
    else:
        # Single user schema (no user_id)
        _show_single_user_stats(cursor)

    conn.close()


def _show_user_stats(cursor, user_id: str) -> None:
    """Show statistics for a single user."""
    # Bursts
    cursor.execute("SELECT COUNT(*) FROM bursts WHERE user_id = ?", (user_id,))
    burst_count = cursor.fetchone()[0]

    cursor.execute(
        "SELECT MIN(start_time), MAX(start_time) FROM bursts WHERE user_id = ?", (user_id,)
    )
    time_row = cursor.fetchone()

    # Statistics
    cursor.execute("SELECT COUNT(*) FROM statistics WHERE user_id = ?", (user_id,))
    stats_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT keycode) FROM statistics WHERE user_id = ?", (user_id,))
    distinct_keys = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(total_presses) FROM statistics WHERE user_id = ?", (user_id,))
    total_presses = cursor.fetchone()[0] or 0

    # Word statistics
    cursor.execute("SELECT COUNT(*) FROM word_statistics WHERE user_id = ?", (user_id,))
    word_stats_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT word) FROM word_statistics WHERE user_id = ?", (user_id,))
    distinct_words = cursor.fetchone()[0]

    cursor.execute(
        "SELECT SUM(observation_count) FROM word_statistics WHERE user_id = ?", (user_id,)
    )
    total_obs = cursor.fetchone()[0] or 0

    # High scores
    cursor.execute("SELECT COUNT(*) FROM high_scores WHERE user_id = ?", (user_id,))
    high_scores_count = cursor.fetchone()[0]

    cursor.execute("SELECT MIN(date), MAX(date) FROM high_scores WHERE user_id = ?", (user_id,))
    scores_row = cursor.fetchone()

    # Daily summaries
    cursor.execute("SELECT COUNT(*) FROM daily_summaries WHERE user_id = ?", (user_id,))
    daily_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT date) FROM daily_summaries WHERE user_id = ?", (user_id,))
    distinct_days = cursor.fetchone()[0]

    cursor.execute("SELECT MIN(date), MAX(date) FROM daily_summaries WHERE user_id = ?", (user_id,))
    daily_row = cursor.fetchone()

    cursor.execute(
        "SELECT SUM(total_keystrokes), SUM(total_bursts) FROM daily_summaries WHERE user_id = ?",
        (user_id,),
    )
    totals_row = cursor.fetchone()

    # Print stats
    print(f"   📊 Bursts: {burst_count:,}")
    if time_row[0]:
        print(
            f"      Time range: {datetime.fromtimestamp(time_row[0] / 1000).strftime('%Y-%m-%d')} to {datetime.fromtimestamp(time_row[1] / 1000).strftime('%Y-%m-%d')}"
        )

    print(f"   📊 Key statistics: {stats_count:,} records, {distinct_keys} distinct keys")
    print(f"      Total key presses: {total_presses:,}")

    print(f"   📊 Word statistics: {word_stats_count:,} records, {distinct_words} distinct words")
    print(f"      Total observations: {total_obs:,}")

    print(f"   📊 High scores: {high_scores_count:,}")
    if scores_row[0]:
        print(f"      Date range: {scores_row[0]} to {scores_row[1]}")

    print(f"   📊 Daily summaries: {daily_count:,} records, {distinct_days} days")
    if daily_row[0]:
        print(f"      Date range: {daily_row[0]} to {daily_row[1]}")
    print(f"      Total keystrokes: {totals_row[0] or 0:,}, bursts: {totals_row[1] or 0:,}")


def _show_single_user_stats(cursor) -> None:
    """Show statistics for single-user schema (no user_id)."""
    # Bursts
    cursor.execute("SELECT COUNT(*) FROM bursts")
    burst_count = cursor.fetchone()[0]

    cursor.execute("SELECT MIN(start_time), MAX(start_time) FROM bursts")
    time_row = cursor.fetchone()

    # Statistics
    cursor.execute("SELECT COUNT(*) FROM statistics")
    stats_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT keycode) FROM statistics")
    distinct_keys = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(total_presses) FROM statistics")
    total_presses = cursor.fetchone()[0] or 0

    # Word statistics
    cursor.execute("SELECT COUNT(*) FROM word_statistics")
    word_stats_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT word) FROM word_statistics")
    distinct_words = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(observation_count) FROM word_statistics")
    total_obs = cursor.fetchone()[0] or 0

    # High scores
    cursor.execute("SELECT COUNT(*) FROM high_scores")
    high_scores_count = cursor.fetchone()[0]

    cursor.execute("SELECT MIN(date), MAX(date) FROM high_scores")
    scores_row = cursor.fetchone()

    # Daily summaries
    cursor.execute("SELECT COUNT(*) FROM daily_summaries")
    daily_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT date) FROM daily_summaries")
    distinct_days = cursor.fetchone()[0]

    cursor.execute("SELECT MIN(date), MAX(date) FROM daily_summaries")
    daily_row = cursor.fetchone()

    cursor.execute("SELECT SUM(total_keystrokes), SUM(total_bursts) FROM daily_summaries")
    totals_row = cursor.fetchone()

    # Print stats
    print(f"   📊 Bursts: {burst_count:,}")
    if time_row[0]:
        print(
            f"      Time range: {datetime.fromtimestamp(time_row[0] / 1000).strftime('%Y-%m-%d')} to {datetime.fromtimestamp(time_row[1] / 1000).strftime('%Y-%m-%d')}"
        )

    print(f"   📊 Key statistics: {stats_count:,} records, {distinct_keys} distinct keys")
    print(f"      Total key presses: {total_presses:,}")

    print(f"   📊 Word statistics: {word_stats_count:,} records, {distinct_words} distinct words")
    print(f"      Total observations: {total_obs:,}")

    print(f"   📊 High scores: {high_scores_count:,}")
    if scores_row[0]:
        print(f"      Date range: {scores_row[0]} to {scores_row[1]}")

    print(f"   📊 Daily summaries: {daily_count:,} records, {distinct_days} days")
    if daily_row[0]:
        print(f"      Date range: {daily_row[0]} to {daily_row[1]}")
    print(f"      Total keystrokes: {totals_row[0] or 0:,}, bursts: {totals_row[1] or 0:,}")


def main():
    parser = argparse.ArgumentParser(
        description="Get quick statistics from local SQLite database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s
  %(prog)s --user-id 123e4567-e89b-12d3-a456-426614174000
        """,
    )

    parser.add_argument("--user-id", metavar="UUID", help="Filter by user ID")

    args = parser.parse_args()

    # Get database path
    db_path = Path.home() / ".local" / "share" / "realtypecoach" / "typing_data.db"

    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        sys.exit(1)

    get_stats(db_path, args.user_id)


if __name__ == "__main__":
    main()
