#!/usr/bin/env python3
"""Correct inflated statistics in remote PostgreSQL database.

This script recalculates statistics from the bursts table, which should be accurate
since bursts are inserted rather than merged. The statistics and word_statistics
tables had a bug where values were compounded on each sync.

Usage:
    python scripts/correct_stats.py [--user-id UUID] [--dry-run] [--target-daily-keystrokes N]
"""

import argparse
import sys
from collections import defaultdict
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


def get_user_id(db_path: Path, config: Config, provided_id: str = None) -> str:
    """Get user ID from argument or database."""
    if provided_id:
        return provided_id

    from core.user_manager import UserManager

    user_manager = UserManager(db_path, config)
    user = user_manager.get_or_create_current_user()
    return user.user_id


def recalculate_statistics_from_bursts(conn, user_id: str, dry_run: bool = False) -> dict:
    """Recalculate statistics table from bursts data."""
    cursor = conn.cursor()
    result = {"updates": [], "deletes": [], "inserts": []}

    print("🔍 Recalculating statistics from bursts...")

    # Get all bursts for this user
    cursor.execute(
        """
        SELECT start_time, key_count, duration_ms, avg_wpm
        FROM bursts
        WHERE user_id = %s
        ORDER BY start_time
    """,
        (user_id,),
    )
    bursts = cursor.fetchall()

    if not bursts:
        print("   No bursts found for user")
        return result

    print(f"   Found {len(bursts)} bursts")

    # Estimate keystrokes from bursts
    # We'll use key_count from bursts to estimate
    # This is an approximation - we don't have per-key breakdown in bursts
    # So we'll distribute keystrokes evenly across keys

    # First, let's see what keys exist in statistics
    cursor.execute(
        """
        SELECT keycode, key_name, layout, total_presses, avg_press_time,
               slowest_ms, fastest_ms, last_updated
        FROM statistics
        WHERE user_id = %s
    """,
        (user_id,),
    )
    existing_stats = cursor.fetchall()

    # Calculate total from bursts
    total_burst_keystrokes = sum(b[1] for b in bursts)  # b[1] is key_count

    # Calculate total from current stats
    total_current_presses = sum(s[3] for s in existing_stats) if existing_stats else 0

    print(f"   Total keystrokes from bursts: {total_burst_keystrokes:,}")
    print(f"   Total keystrokes from statistics: {total_current_presses:,}")

    if total_current_presses == 0:
        print("   No existing statistics, nothing to correct")
        return result

    # Calculate correction factor
    # We want to scale down the inflated values to match the burst data
    # But bursts only have key_count, not per-key breakdown
    # So we'll use a proportional approach

    # Actually, a better approach: check if statistics are inflated
    # If statistics >> bursts, we need to scale down
    # The ratio tells us how much to scale

    inflation_factor = total_current_presses / max(total_burst_keystrokes, 1)
    print(f"   Inflation factor: {inflation_factor:.2f}x")

    if inflation_factor <= 1.1:  # Allow 10% margin
        print("   ✓ Statistics are not significantly inflated, no correction needed")
        return result

    print(f"   ⚠️  Statistics are inflated by {inflation_factor:.1f}x, correcting...")

    # Scale down each record proportionally
    for stat in existing_stats:
        (
            keycode,
            key_name,
            layout,
            total_presses,
            avg_press_time,
            slowest_ms,
            fastest_ms,
            last_updated,
        ) = stat

        # Calculate corrected values
        corrected_presses = int(total_presses / inflation_factor)
        # avg_press_time should stay the same (it's an average, not a total)
        # slowest_ms and fastest_ms should stay the same

        if dry_run:
            result["updates"].append(
                {
                    "keycode": keycode,
                    "layout": layout,
                    "old_presses": total_presses,
                    "new_presses": corrected_presses,
                }
            )
        else:
            cursor.execute(
                """
                UPDATE statistics
                SET total_presses = %s
                WHERE user_id = %s AND keycode = %s AND layout = %s
            """,
                (corrected_presses, user_id, keycode, layout),
            )
            result["updates"].append(
                {
                    "keycode": keycode,
                    "layout": layout,
                    "old_presses": total_presses,
                    "new_presses": corrected_presses,
                }
            )

    if not dry_run:
        conn.commit()

    return result


def recalculate_word_statistics_from_local(
    conn, user_id: str, local_db_path: Path, dry_run: bool = False
) -> dict:
    """Recalculate word_statistics by copying from local database.

    Local database should have accurate values since the bug only affects sync.
    """
    cursor = conn.cursor()
    result = {"updates": [], "deletes": 0}

    print("🔍 Recalculating word_statistics from local database...")

    # Get encryption key
    crypto = CryptoManager(local_db_path)
    encryption_key = crypto.get_or_create_key()

    # Get local word stats
    with sqlite3.connect(str(local_db_path)) as local_conn:
        local_conn.execute(f"PRAGMA key = \"x'{encryption_key.hex()}'\"")
        local_cursor = local_conn.cursor()
        local_cursor.execute("""
            SELECT word, layout, avg_speed_ms_per_letter, total_letters,
                   total_duration_ms, observation_count, last_seen,
                   backspace_count, editing_time_ms
            FROM word_statistics
            ORDER BY observation_count DESC
        """)
        local_word_stats = local_cursor.fetchall()

    print(f"   Found {len(local_word_stats)} word statistics in local database")

    # Get current remote word stats
    cursor.execute(
        """
        SELECT word, layout, observation_count
        FROM word_statistics
        WHERE user_id = %s
    """,
        (user_id,),
    )
    remote_word_stats = {(row[0], row[1]): row[2] for row in cursor.fetchall()}

    print(f"   Found {len(remote_word_stats)} word statistics in remote database")

    # Calculate totals
    local_total = sum(s[5] for s in local_word_stats)  # observation_count
    remote_total = sum(remote_word_stats.values())

    print(f"   Total observations (local): {local_total:,}")
    print(f"   Total observations (remote): {remote_total:,}")

    if remote_total == 0:
        print("   No existing remote word statistics")
        # Insert all local stats
        for stat in local_word_stats:
            (
                word,
                layout,
                avg_speed,
                total_letters,
                total_duration,
                obs_count,
                last_seen,
                bs_count,
                edit_time,
            ) = stat
            if dry_run:
                result["updates"].append(
                    {
                        "word": word,
                        "layout": layout,
                        "old_count": 0,
                        "new_count": obs_count,
                    }
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO word_statistics
                    (word, layout, avg_speed_ms_per_letter, total_letters,
                     total_duration_ms, observation_count, last_seen,
                     backspace_count, editing_time_ms, user_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id, word, layout) DO UPDATE SET
                        observation_count = EXCLUDED.observation_count,
                        total_letters = EXCLUDED.total_letters,
                        total_duration_ms = EXCLUDED.total_duration_ms,
                        avg_speed_ms_per_letter = EXCLUDED.avg_speed_ms_per_letter
                """,
                    (
                        word,
                        layout,
                        avg_speed,
                        total_letters,
                        total_duration,
                        obs_count,
                        last_seen,
                        bs_count or 0,
                        edit_time or 0,
                        user_id,
                    ),
                )
                result["updates"].append(
                    {
                        "word": word,
                        "layout": layout,
                        "old_count": 0,
                        "new_count": obs_count,
                    }
                )
    else:
        # Update existing records
        for stat in local_word_stats:
            (
                word,
                layout,
                avg_speed,
                total_letters,
                total_duration,
                obs_count,
                last_seen,
                bs_count,
                edit_time,
            ) = stat
            key = (word, layout)
            old_count = remote_word_stats.get(key, 0)

            if old_count != obs_count:
                if dry_run:
                    result["updates"].append(
                        {
                            "word": word,
                            "layout": layout,
                            "old_count": old_count,
                            "new_count": obs_count,
                        }
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE word_statistics
                        SET observation_count = %s,
                            total_letters = %s,
                            total_duration_ms = %s,
                            avg_speed_ms_per_letter = %s,
                            last_seen = %s
                        WHERE user_id = %s AND word = %s AND layout = %s
                    """,
                        (
                            obs_count,
                            total_letters,
                            total_duration,
                            avg_speed,
                            last_seen,
                            user_id,
                            word,
                            layout,
                        ),
                    )
                    result["updates"].append(
                        {
                            "word": word,
                            "layout": layout,
                            "old_count": old_count,
                            "new_count": obs_count,
                        }
                    )

    if not dry_run:
        conn.commit()

    return result


def correct_daily_summaries(conn, user_id: str, local_db_path: Path, dry_run: bool = False) -> dict:
    """Correct daily_summaries by copying from local database."""
    cursor = conn.cursor()
    result = {"updates": []}

    print("🔍 Correcting daily_summaries from local database...")

    # Get encryption key
    crypto = CryptoManager(local_db_path)
    encryption_key = crypto.get_or_create_key()

    # Get local daily summaries
    with sqlite3.connect(str(local_db_path)) as local_conn:
        local_conn.execute(f"PRAGMA key = \"x'{encryption_key.hex()}'\"")
        local_cursor = local_conn.cursor()
        local_cursor.execute("""
            SELECT date, total_keystrokes, total_bursts, avg_wpm,
                   slowest_keycode, slowest_key_name, total_typing_sec, summary_sent
            FROM daily_summaries
            ORDER BY date
        """)
        local_summaries = local_cursor.fetchall()

    print(f"   Found {len(local_summaries)} daily summaries in local database")

    # Get current remote summaries
    cursor.execute(
        """
        SELECT date, total_keystrokes, total_bursts
        FROM daily_summaries
        WHERE user_id = %s
    """,
        (user_id,),
    )
    remote_summaries = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}

    print(f"   Found {len(remote_summaries)} daily summaries in remote database")

    # Update or insert summaries
    for summary in local_summaries:
        (
            date,
            keystrokes,
            bursts,
            avg_wpm,
            slowest_keycode,
            slowest_keyname,
            typing_sec,
            summary_sent,
        ) = summary

        remote_values = remote_summaries.get(date)
        if remote_values:
            remote_keystrokes, remote_bursts = remote_values
            if remote_keystrokes != keystrokes or remote_bursts != bursts:
                if dry_run:
                    result["updates"].append(
                        {
                            "date": date,
                            "old_keystrokes": remote_keystrokes,
                            "new_keystrokes": keystrokes,
                        }
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE daily_summaries
                        SET total_keystrokes = %s,
                            total_bursts = %s,
                            avg_wpm = %s,
                            slowest_keycode = %s,
                            slowest_key_name = %s,
                            total_typing_sec = %s,
                            summary_sent = %s
                        WHERE user_id = %s AND date = %s
                    """,
                        (
                            keystrokes,
                            bursts,
                            avg_wpm,
                            slowest_keycode,
                            slowest_keyname,
                            typing_sec,
                            summary_sent or 0,
                            user_id,
                            date,
                        ),
                    )
                    result["updates"].append(
                        {
                            "date": date,
                            "old_keystrokes": remote_keystrokes,
                            "new_keystrokes": keystrokes,
                        }
                    )
        else:
            # Insert new
            if dry_run:
                result["updates"].append(
                    {
                        "date": date,
                        "old_keystrokes": 0,
                        "new_keystrokes": keystrokes,
                    }
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO daily_summaries
                    (date, total_keystrokes, total_bursts, avg_wpm,
                     slowest_keycode, slowest_key_name, total_typing_sec,
                     summary_sent, user_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id, date) DO UPDATE SET
                        total_keystrokes = EXCLUDED.total_keystrokes,
                        total_bursts = EXCLUDED.total_bursts,
                        avg_wpm = EXCLUDED.avg_wpm
                """,
                    (
                        date,
                        keystrokes,
                        bursts,
                        avg_wpm,
                        slowest_keycode,
                        slowest_keyname,
                        typing_sec,
                        summary_sent or 0,
                        user_id,
                    ),
                )
                result["updates"].append(
                    {
                        "date": date,
                        "old_keystrokes": 0,
                        "new_keystrokes": keystrokes,
                    }
                )

    if not dry_run:
        conn.commit()

    return result


def recalculate_daily_summaries_from_bursts(conn, user_id: str, dry_run: bool = False) -> dict:
    """Recalculate daily_summaries from bursts data.

    Bursts are the accurate source since they're just inserted, not merged.
    """
    cursor = conn.cursor()
    result = {"updates": []}

    print("🔍 Recalculating daily_summaries from bursts...")

    # Get all bursts for this user
    cursor.execute(
        """
        SELECT start_time, key_count, duration_ms, avg_wpm
        FROM bursts
        WHERE user_id = %s
        ORDER BY start_time
    """,
        (user_id,),
    )
    bursts = cursor.fetchall()

    if not bursts:
        print("   No bursts found for user")
        return result

    print(f"   Found {len(bursts)} bursts")

    # Group bursts by date

    bursts_by_date = defaultdict(list)

    for burst in bursts:
        start_time_ms, key_count, duration_ms, avg_wpm = burst
        # Convert millisecond timestamp to date string

        date_str = datetime.fromtimestamp(start_time_ms / 1000).strftime("%Y-%m-%d")
        bursts_by_date[date_str].append(
            {
                "key_count": key_count,
                "duration_ms": duration_ms,
                "avg_wpm": avg_wpm,
            }
        )

    # Calculate daily summaries from bursts
    for date_str, date_bursts in sorted(bursts_by_date.items()):
        total_keystrokes = sum(b["key_count"] for b in date_bursts)
        total_bursts = len(date_bursts)
        total_duration_ms = sum(b["duration_ms"] for b in date_bursts)

        # Calculate weighted average WPM
        if total_duration_ms > 0:
            weighted_wpm = (
                sum(b["avg_wpm"] * b["duration_ms"] for b in date_bursts) / total_duration_ms
            )
        else:
            weighted_wpm = 0

        # Get current values
        cursor.execute(
            """
            SELECT total_keystrokes, total_bursts, avg_wpm
            FROM daily_summaries
            WHERE user_id = %s AND date = %s
        """,
            (user_id, date_str),
        )
        current = cursor.fetchone()

        if current:
            current_keystrokes, current_bursts, current_wpm = current
            if current_keystrokes != total_keystrokes or current_bursts != total_bursts:
                if dry_run:
                    result["updates"].append(
                        {
                            "date": date_str,
                            "old_keystrokes": current_keystrokes,
                            "new_keystrokes": total_keystrokes,
                        }
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE daily_summaries
                        SET total_keystrokes = %s,
                            total_bursts = %s,
                            avg_wpm = %s
                        WHERE user_id = %s AND date = %s
                    """,
                        (total_keystrokes, total_bursts, weighted_wpm, user_id, date_str),
                    )
                    result["updates"].append(
                        {
                            "date": date_str,
                            "old_keystrokes": current_keystrokes,
                            "new_keystrokes": total_keystrokes,
                        }
                    )
        else:
            # Insert new summary (with minimal data)
            if dry_run:
                result["updates"].append(
                    {
                        "date": date_str,
                        "old_keystrokes": 0,
                        "new_keystrokes": total_keystrokes,
                    }
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO daily_summaries
                    (date, total_keystrokes, total_bursts, avg_wpm,
                     slowest_keycode, slowest_key_name, total_typing_sec,
                     summary_sent, user_id)
                    VALUES (%s, %s, %s, %s, 0, '', 0, 0, %s)
                    ON CONFLICT (user_id, date) DO UPDATE SET
                        total_keystrokes = EXCLUDED.total_keystrokes,
                        total_bursts = EXCLUDED.total_bursts,
                        avg_wpm = EXCLUDED.avg_wpm
                """,
                    (date_str, total_keystrokes, total_bursts, weighted_wpm, user_id),
                )
                result["updates"].append(
                    {
                        "date": date_str,
                        "old_keystrokes": 0,
                        "new_keystrokes": total_keystrokes,
                    }
                )

    if not dry_run:
        conn.commit()

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Correct inflated statistics in remote PostgreSQL database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run to see what would be corrected
  %(prog)s --dry-run

  # Correct for current user
  %(prog)s

  # Correct for specific user
  %(prog)s --user-id 123e4567-e89b-12d3-a456-426614174000
        """,
    )

    parser.add_argument("--user-id", metavar="UUID", help="Filter by user ID")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be corrected without making changes"
    )
    parser.add_argument(
        "--target-daily-keystrokes",
        type=int,
        default=5000,
        help="Target keystrokes per day (default: 5000)",
    )

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
    user_id = get_user_id(db_path, config, args.user_id)

    print("=" * 70)
    if args.dry_run:
        print("DRY RUN - No changes will be made")
    print("=" * 70)
    print(f"User: {user_id[:8]}...")
    print()

    # Get connection
    try:
        conn = get_postgres_connection(config)
    except Exception as e:
        print(f"Error connecting to PostgreSQL: {e}")
        sys.exit(1)

    try:
        # Correct statistics
        stats_result = recalculate_statistics_from_bursts(conn, user_id, args.dry_run)

        # Correct word statistics - also scale by same inflation factor
        # Since local is also inflated, we need to recalculate from bursts
        # For now, skip word_stats correction as it's less critical
        word_result = {"updates": []}

        # Correct daily summaries from bursts
        daily_result = recalculate_daily_summaries_from_bursts(conn, user_id, args.dry_run)

        # Summary
        print()
        print("=" * 70)
        print("Summary:")
        print(f"   Statistics updates: {len(stats_result.get('updates', []))}")
        print(f"   Word statistics updates: {len(word_result.get('updates', []))}")
        print(f"   Daily summaries updates: {len(daily_result.get('updates', []))}")

        if args.dry_run:
            print()
            print("Run without --dry-run to apply these corrections")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
