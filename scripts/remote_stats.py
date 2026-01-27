#!/usr/bin/env python3
"""Get quick statistics from remote PostgreSQL database.

Usage:
    python scripts/remote_stats.py
    python scripts/remote_stats.py --user-id <uuid>
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg2

from utils.config import Config
from utils.crypto import CryptoManager


def get_connection(config: Config):
    """Get PostgreSQL connection."""
    return psycopg2.connect(
        host=config.get("postgres_host", ""),
        port=config.get_int("postgres_port", 5432),
        dbname=config.get("postgres_database", "realtypecoach"),
        user=config.get("postgres_user", ""),
        password=get_postgres_password(config),
        sslmode=config.get("postgres_sslmode", "require"),
    )


def get_postgres_password(config: Config) -> str:
    """Get PostgreSQL password from keyring or secret file."""
    # Try CryptoManager which handles both keyring and secret file
    db_path = Path.home() / ".local" / "share" / "realtypecoach" / "typing_data.db"
    crypto = CryptoManager(db_path)
    password = crypto.get_postgres_password()
    if password:
        return password

    raise RuntimeError(
        "PostgreSQL password not found in keyring or secret file. "
        "Please configure it in the app settings first."
    )


def get_stats(conn, user_id: str | None = None):
    """Get statistics from remote database."""
    cursor = conn.cursor()

    # User filter
    user_filter = f"WHERE user_id = '{user_id}'" if user_id else ""

    print("=" * 70)
    print("Remote PostgreSQL Database Statistics")
    print("=" * 70)

    # Show all users in database
    cursor.execute("""
        SELECT DISTINCT user_id
        FROM bursts
        ORDER BY user_id
    """)
    all_users = [row[0] for row in cursor.fetchall()]

    if user_id:
        # Single user mode
        print(f"👤 User: {user_id[:8]}...")
        print()
        _show_user_stats(cursor, user_id)
    else:
        # All users mode
        for uid in all_users:
            print(f"👤 User: {uid[:8]}...")
            _show_user_stats(cursor, uid)
            print()


def _show_user_stats(cursor, user_id: str) -> None:
    """Show statistics for a single user."""
    # Bursts
    cursor.execute("SELECT COUNT(*) FROM bursts WHERE user_id = %s", (user_id,))
    burst_count = cursor.fetchone()[0]

    cursor.execute(
        "SELECT MIN(start_time), MAX(start_time) FROM bursts WHERE user_id = %s", (user_id,)
    )
    time_row = cursor.fetchone()

    # Statistics
    cursor.execute("SELECT COUNT(*) FROM statistics WHERE user_id = %s", (user_id,))
    stats_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT keycode) FROM statistics WHERE user_id = %s", (user_id,))
    distinct_keys = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(total_presses) FROM statistics WHERE user_id = %s", (user_id,))
    total_presses = cursor.fetchone()[0] or 0

    # Word statistics
    cursor.execute("SELECT COUNT(*) FROM word_statistics WHERE user_id = %s", (user_id,))
    word_stats_count = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(DISTINCT word) FROM word_statistics WHERE user_id = %s", (user_id,)
    )
    distinct_words = cursor.fetchone()[0]

    cursor.execute(
        "SELECT SUM(observation_count) FROM word_statistics WHERE user_id = %s", (user_id,)
    )
    total_obs = cursor.fetchone()[0] or 0

    # High scores
    cursor.execute("SELECT COUNT(*) FROM high_scores WHERE user_id = %s", (user_id,))
    high_scores_count = cursor.fetchone()[0]

    cursor.execute("SELECT MIN(date), MAX(date) FROM high_scores WHERE user_id = %s", (user_id,))
    scores_row = cursor.fetchone()

    # Daily summaries
    cursor.execute("SELECT COUNT(*) FROM daily_summaries WHERE user_id = %s", (user_id,))
    daily_count = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(DISTINCT date) FROM daily_summaries WHERE user_id = %s", (user_id,)
    )
    distinct_days = cursor.fetchone()[0]

    cursor.execute(
        "SELECT MIN(date), MAX(date) FROM daily_summaries WHERE user_id = %s", (user_id,)
    )
    daily_row = cursor.fetchone()

    cursor.execute(
        "SELECT SUM(total_keystrokes), SUM(total_bursts) FROM daily_summaries WHERE user_id = %s",
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


def main():
    parser = argparse.ArgumentParser(
        description="Get quick statistics from remote PostgreSQL database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s
  %(prog)s --user-id 123e4567-e89b-12d3-a456-426614174000
        """,
    )

    parser.add_argument("--user-id", metavar="UUID", help="Filter by user ID")

    args = parser.parse_args()

    # Get database path for config
    db_path = Path.home() / ".local" / "share" / "realtypecoach" / "typing_data.db"

    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        sys.exit(1)

    # Load config
    try:
        config = Config(db_path)
    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(1)

    if not config.get_bool("postgres_sync_enabled", False):
        print("PostgreSQL sync is not enabled in config")
        sys.exit(1)

    # Get connection
    try:
        conn = get_connection(config)
    except Exception as e:
        print(f"Error connecting to PostgreSQL: {e}")
        sys.exit(1)

    try:
        get_stats(conn, args.user_id)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
