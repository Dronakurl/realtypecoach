#!/usr/bin/env python3
"""Compare local and remote database statistics.

Usage:
    python scripts/compare_stats.py
    python scripts/compare_stats.py --user-id <uuid>
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg2
import sqlcipher3 as sqlite3

from utils.config import Config
from utils.crypto import CryptoManager


def get_postgres_connection(config: Config):
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
    db_path = Path.home() / ".local" / "share" / "realtypecoach" / "typing_data.db"
    crypto = CryptoManager(db_path)
    password = crypto.get_postgres_password()
    if password:
        return password

    raise RuntimeError(
        "PostgreSQL password not found in keyring or secret file. "
        "Please configure it in the app settings first."
    )


def get_local_stats(db_path: Path, config: Config, user_id: str = None) -> dict:
    """Get statistics from local SQLite database."""
    stats = {}

    # Get encryption key
    crypto = CryptoManager(db_path)
    encryption_key = crypto.get_or_create_key()

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(f"PRAGMA key = \"x'{encryption_key.hex()}'\"")
        cursor = conn.cursor()

        # Bursts
        cursor.execute("SELECT COUNT(*) FROM bursts")
        stats["bursts_count"] = cursor.fetchone()[0]

        cursor.execute("SELECT MIN(start_time), MAX(start_time) FROM bursts")
        row = cursor.fetchone()
        stats["bursts_time_range"] = row

        # Statistics
        cursor.execute("SELECT COUNT(*) FROM statistics")
        stats["stats_count"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT keycode) FROM statistics")
        stats["distinct_keys"] = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(total_presses) FROM statistics")
        stats["total_presses"] = cursor.fetchone()[0] or 0

        # Top keys by presses
        cursor.execute("""
            SELECT key_name, total_presses
            FROM statistics
            ORDER BY total_presses DESC
            LIMIT 10
        """)
        stats["top_keys"] = cursor.fetchall()

        # Word statistics
        cursor.execute("SELECT COUNT(*) FROM word_statistics")
        stats["word_stats_count"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT word) FROM word_statistics")
        stats["distinct_words"] = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(observation_count) FROM word_statistics")
        stats["total_observations"] = cursor.fetchone()[0] or 0

        # Top words by observations
        cursor.execute("""
            SELECT word, observation_count
            FROM word_statistics
            ORDER BY observation_count DESC
            LIMIT 10
        """)
        stats["top_words"] = cursor.fetchall()

        # High scores
        cursor.execute("SELECT COUNT(*) FROM high_scores")
        stats["high_scores_count"] = cursor.fetchone()[0]

        cursor.execute("SELECT MIN(date), MAX(date) FROM high_scores")
        stats["high_scores_range"] = cursor.fetchone()

        # Daily summaries
        cursor.execute("SELECT COUNT(*) FROM daily_summaries")
        stats["daily_count"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT date) FROM daily_summaries")
        stats["distinct_days"] = cursor.fetchone()[0]

        cursor.execute("SELECT MIN(date), MAX(date) FROM daily_summaries")
        stats["daily_range"] = cursor.fetchone()

        cursor.execute("SELECT SUM(total_keystrokes), SUM(total_bursts) FROM daily_summaries")
        row = cursor.fetchone()
        stats["daily_keystrokes"] = row[0] or 0
        stats["daily_bursts"] = row[1] or 0

    return stats


def get_remote_stats(conn, user_id: str) -> dict:
    """Get statistics from remote PostgreSQL database."""
    stats = {}
    cursor = conn.cursor()

    # Bursts
    cursor.execute("SELECT COUNT(*) FROM bursts WHERE user_id = %s", (user_id,))
    stats["bursts_count"] = cursor.fetchone()[0]

    cursor.execute(
        "SELECT MIN(start_time), MAX(start_time) FROM bursts WHERE user_id = %s", (user_id,)
    )
    stats["bursts_time_range"] = cursor.fetchone()

    # Statistics
    cursor.execute("SELECT COUNT(*) FROM statistics WHERE user_id = %s", (user_id,))
    stats["stats_count"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT keycode) FROM statistics WHERE user_id = %s", (user_id,))
    stats["distinct_keys"] = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(total_presses) FROM statistics WHERE user_id = %s", (user_id,))
    stats["total_presses"] = cursor.fetchone()[0] or 0

    # Top keys by presses
    cursor.execute(
        """
        SELECT key_name, total_presses
        FROM statistics
        WHERE user_id = %s
        ORDER BY total_presses DESC
        LIMIT 10
    """,
        (user_id,),
    )
    stats["top_keys"] = cursor.fetchall()

    # Word statistics
    cursor.execute("SELECT COUNT(*) FROM word_statistics WHERE user_id = %s", (user_id,))
    stats["word_stats_count"] = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(DISTINCT word) FROM word_statistics WHERE user_id = %s", (user_id,)
    )
    stats["distinct_words"] = cursor.fetchone()[0]

    cursor.execute(
        "SELECT SUM(observation_count) FROM word_statistics WHERE user_id = %s", (user_id,)
    )
    stats["total_observations"] = cursor.fetchone()[0] or 0

    # Top words by observations
    cursor.execute(
        """
        SELECT word, observation_count
        FROM word_statistics
        WHERE user_id = %s
        ORDER BY observation_count DESC
        LIMIT 10
    """,
        (user_id,),
    )
    stats["top_words"] = cursor.fetchall()

    # High scores
    cursor.execute("SELECT COUNT(*) FROM high_scores WHERE user_id = %s", (user_id,))
    stats["high_scores_count"] = cursor.fetchone()[0]

    cursor.execute("SELECT MIN(date), MAX(date) FROM high_scores WHERE user_id = %s", (user_id,))
    stats["high_scores_range"] = cursor.fetchone()

    # Daily summaries
    cursor.execute("SELECT COUNT(*) FROM daily_summaries WHERE user_id = %s", (user_id,))
    stats["daily_count"] = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(DISTINCT date) FROM daily_summaries WHERE user_id = %s", (user_id,)
    )
    stats["distinct_days"] = cursor.fetchone()[0]

    cursor.execute(
        "SELECT MIN(date), MAX(date) FROM daily_summaries WHERE user_id = %s", (user_id,)
    )
    stats["daily_range"] = cursor.fetchone()

    cursor.execute(
        "SELECT SUM(total_keystrokes), SUM(total_bursts) FROM daily_summaries WHERE user_id = %s",
        (user_id,),
    )
    row = cursor.fetchone()
    stats["daily_keystrokes"] = row[0] or 0
    stats["daily_bursts"] = row[1] or 0

    return stats


def format_number(n: int) -> str:
    """Format number with thousands separator."""
    return f"{n:,}"


def compare_and_show(local_stats: dict, remote_stats: dict, user_id: str) -> None:
    """Compare and display local vs remote statistics."""
    print("=" * 80)
    print(f"Local vs Remote Comparison for user {user_id[:8]}...")
    print("=" * 80)
    print()

    # Bursts comparison
    print("📊 Bursts:")
    print(f"   Local:  {format_number(local_stats['bursts_count'])}")
    print(f"   Remote: {format_number(remote_stats['bursts_count'])}")
    if local_stats["bursts_time_range"][0]:
        local_start = datetime.fromtimestamp(local_stats["bursts_time_range"][0] / 1000).strftime(
            "%Y-%m-%d"
        )
        local_end = datetime.fromtimestamp(local_stats["bursts_time_range"][1] / 1000).strftime(
            "%Y-%m-%d"
        )
        print(f"   Range:  {local_start} to {local_end}")
    if remote_stats["bursts_time_range"][0]:
        remote_start = datetime.fromtimestamp(remote_stats["bursts_time_range"][0] / 1000).strftime(
            "%Y-%m-%d"
        )
        remote_end = datetime.fromtimestamp(remote_stats["bursts_time_range"][1] / 1000).strftime(
            "%Y-%m-%d"
        )
        print(f"   Range:  {remote_start} to {remote_end}")
    print()

    # Key statistics comparison
    print("📊 Key Statistics:")
    print(
        f"   Local:  {format_number(local_stats['stats_count'])} records, {local_stats['distinct_keys']} distinct keys"
    )
    print(
        f"   Remote: {format_number(remote_stats['stats_count'])} records, {remote_stats['distinct_keys']} distinct keys"
    )
    print()
    print("   Total key presses:")
    print(f"   Local:  {format_number(local_stats['total_presses'])}")
    print(f"   Remote: {format_number(remote_stats['total_presses'])}")

    # Check for mismatch
    diff = remote_stats["total_presses"] - local_stats["total_presses"]
    if diff != 0:
        pct = (diff / max(local_stats["total_presses"], 1)) * 100
        print(f"   ⚠️  Difference: {format_number(abs(diff))} ({pct:+.1f}%)")

    # Top keys comparison
    print()
    print("   Top 5 keys by presses (Local | Remote):")
    for i in range(min(5, len(local_stats["top_keys"]), len(remote_stats["top_keys"]))):
        local_key, local_count = local_stats["top_keys"][i]
        remote_key, remote_count = remote_stats["top_keys"][i]
        print(
            f"      {i + 1}. {local_key:15s}: Local={format_number(local_count):>12} | Remote={format_number(remote_count):>12}"
        )
    print()

    # Word statistics comparison
    print("📊 Word Statistics:")
    print(
        f"   Local:  {format_number(local_stats['word_stats_count'])} records, {local_stats['distinct_words']} distinct words"
    )
    print(
        f"   Remote: {format_number(remote_stats['word_stats_count'])} records, {remote_stats['distinct_words']} distinct words"
    )
    print()
    print("   Total observations:")
    print(f"   Local:  {format_number(local_stats['total_observations'])}")
    print(f"   Remote: {format_number(remote_stats['total_observations'])}")
    print()

    # Top words comparison
    print("   Top 5 words by observations (Local | Remote):")
    for i in range(min(5, len(local_stats["top_words"]), len(remote_stats["top_words"]))):
        local_word, local_count = local_stats["top_words"][i]
        remote_word, remote_count = remote_stats["top_words"][i]
        print(
            f"      {i + 1}. {local_word:15s}: Local={format_number(local_count):>12} | Remote={format_number(remote_count):>12}"
        )
    print()

    # Daily summaries comparison
    print("📊 Daily Summaries:")
    print(
        f"   Local:  {format_number(local_stats['daily_count'])} records, {local_stats['distinct_days']} days"
    )
    print(
        f"   Remote: {format_number(remote_stats['daily_count'])} records, {remote_stats['distinct_days']} days"
    )
    print()
    print("   Total keystrokes from daily summaries:")
    print(f"   Local:  {format_number(local_stats['daily_keystrokes'])}")
    print(f"   Remote: {format_number(remote_stats['daily_keystrokes'])}")

    # Calculate average per day
    if local_stats["distinct_days"] > 0:
        local_avg = local_stats["daily_keystrokes"] / local_stats["distinct_days"]
        print(f"   Average per day (local): {format_number(int(local_avg))}")
    if remote_stats["distinct_days"] > 0:
        remote_avg = remote_stats["daily_keystrokes"] / remote_stats["distinct_days"]
        print(f"   Average per day (remote): {format_number(int(remote_avg))}")
    print()

    # Sync status
    print("🔄 Sync Status:")
    local_keys = set((k, v) for k, v in local_stats["top_keys"])
    remote_keys = set((k, v) for k, v in remote_stats["top_keys"])
    in_sync = (
        local_stats["bursts_count"] == remote_stats["bursts_count"]
        and local_stats["total_presses"] == remote_stats["total_presses"]
        and local_stats["total_observations"] == remote_stats["total_observations"]
        and local_stats["daily_keystrokes"] == remote_stats["daily_keystrokes"]
    )

    if in_sync:
        print("   ✓ Local and remote are in sync")
    else:
        print("   ⚠️  Local and remote are NOT in sync - run 'just sync'")


def main():
    parser = argparse.ArgumentParser(
        description="Compare local and remote database statistics",
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

    # Get user ID
    if args.user_id:
        user_id = args.user_id
    else:
        # Get current user
        from core.user_manager import UserManager

        user_manager = UserManager(db_path, config)
        user = user_manager.get_or_create_current_user()
        user_id = user.user_id

    # Get local stats
    local_stats = get_local_stats(db_path, config, user_id)

    # Get remote stats
    try:
        conn = get_postgres_connection(config)
        remote_stats = get_remote_stats(conn, user_id)
        conn.close()
    except Exception as e:
        print(f"Error connecting to PostgreSQL: {e}")
        sys.exit(1)

    # Compare and show
    compare_and_show(local_stats, remote_stats, user_id)


if __name__ == "__main__":
    main()
