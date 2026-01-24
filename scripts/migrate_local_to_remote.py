#!/usr/bin/env python3
"""Migrate RealTypeCoach data from local SQLite to remote PostgreSQL.

This script reads all data from the local SQLite database and
bulk inserts it into a remote PostgreSQL database.

Usage:
    python migrate_local_to_remote.py

Prerequisites:
    - Local SQLite database at ~/.local/share/realtypecoach/typing_data.db
    - PostgreSQL database configured and running
    - psycopg2-binary installed
"""

import logging
import sys
from pathlib import Path

import sqlcipher3 as sqlite3

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import psycopg2
    from psycopg2.extras import execute_batch
except ImportError:
    print("Error: psycopg2 is not installed.")
    print("Install it with: pip install psycopg2-binary")
    sys.exit(1)

from utils.config import Config
from utils.crypto import CryptoManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("migrate")


def get_sqlite_data(db_path: Path, crypto) -> dict:
    """Read all data from SQLite database.

    Args:
        db_path: Path to SQLite database
        crypto: CryptoManager instance for decryption

    Returns:
        Dictionary with all data tables
    """
    data = {
        "bursts": [],
        "statistics": [],
        "high_scores": [],
        "daily_summaries": [],
        "word_statistics": [],
    }

    # Get encryption key
    encryption_key = crypto.get_key()
    if encryption_key is None:
        raise RuntimeError("Cannot get database encryption key")

    # Connect to SQLite
    conn = sqlite3.connect(db_path)
    conn.execute(f"PRAGMA key = \"x'{encryption_key.hex()}'\"")

    # Verify access
    try:
        conn.execute("SELECT count(*) FROM sqlite_master")
    except sqlite3.DatabaseError as e:
        conn.close()
        raise RuntimeError(f"Cannot decrypt database: {e}")

    cursor = conn.cursor()

    # Read bursts
    log.info("Reading bursts...")
    cursor.execute("SELECT * FROM bursts")
    columns = [desc[0] for desc in cursor.description]
    for row in cursor.fetchall():
        data["bursts"].append(dict(zip(columns, row, strict=False)))

    # Read statistics
    log.info("Reading statistics...")
    cursor.execute("SELECT * FROM statistics")
    columns = [desc[0] for desc in cursor.description]
    for row in cursor.fetchall():
        data["statistics"].append(dict(zip(columns, row, strict=False)))

    # Read high scores
    log.info("Reading high scores...")
    cursor.execute("SELECT * FROM high_scores")
    columns = [desc[0] for desc in cursor.description]
    for row in cursor.fetchall():
        data["high_scores"].append(dict(zip(columns, row, strict=False)))

    # Read daily summaries
    log.info("Reading daily summaries...")
    cursor.execute("SELECT * FROM daily_summaries")
    columns = [desc[0] for desc in cursor.description]
    for row in cursor.fetchall():
        data["daily_summaries"].append(dict(zip(columns, row, strict=False)))

    # Read word statistics
    log.info("Reading word statistics...")
    cursor.execute("SELECT * FROM word_statistics")
    columns = [desc[0] for desc in cursor.description]
    for row in cursor.fetchall():
        data["word_statistics"].append(dict(zip(columns, row, strict=False)))

    conn.close()

    log.info(f"Read {len(data['bursts'])} bursts")
    log.info(f"Read {len(data['statistics'])} statistics")
    log.info(f"Read {len(data['high_scores'])} high scores")
    log.info(f"Read {len(data['daily_summaries'])} daily summaries")
    log.info(f"Read {len(data['word_statistics'])} word statistics")

    return data


def migrate_to_postgres(data: dict, pg_config: dict) -> None:
    """Migrate data to PostgreSQL.

    Args:
        data: Dictionary with all data tables
        pg_config: PostgreSQL connection configuration
    """
    # Connect to PostgreSQL
    conn = psycopg2.connect(**pg_config)
    cursor = conn.cursor()

    try:
        # Migrate bursts
        log.info("Migrating bursts to PostgreSQL...")
        if data["bursts"]:
            execute_batch(
                cursor,
                """
                INSERT INTO bursts
                (start_time, end_time, key_count, duration_ms, avg_wpm,
                 qualifies_for_high_score, backspace_count, net_key_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """,
                [
                    (
                        b["start_time"],
                        b["end_time"],
                        b["key_count"],
                        b["duration_ms"],
                        b["avg_wpm"],
                        b["qualifies_for_high_score"],
                        b.get("backspace_count", 0),
                        b.get("net_key_count", 0),
                    )
                    for b in data["bursts"]
                ],
            )
            log.info(f"Migrated {len(data['bursts'])} bursts")

        # Migrate statistics
        log.info("Migrating statistics to PostgreSQL...")
        if data["statistics"]:
            execute_batch(
                cursor,
                """
                INSERT INTO statistics
                (keycode, key_name, layout, avg_press_time, total_presses,
                 slowest_ms, fastest_ms, last_updated)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (keycode, layout) DO UPDATE SET
                    avg_press_time = EXCLUDED.avg_press_time,
                    total_presses = EXCLUDED.total_presses,
                    slowest_ms = EXCLUDED.slowest_ms,
                    fastest_ms = EXCLUDED.fastest_ms,
                    last_updated = EXCLUDED.last_updated
            """,
                [
                    (
                        s["keycode"],
                        s["key_name"],
                        s["layout"],
                        s["avg_press_time"],
                        s["total_presses"],
                        s["slowest_ms"],
                        s["fastest_ms"],
                        s["last_updated"],
                    )
                    for s in data["statistics"]
                ],
            )
            log.info(f"Migrated {len(data['statistics'])} statistics")

        # Migrate high scores
        log.info("Migrating high scores to PostgreSQL...")
        if data["high_scores"]:
            execute_batch(
                cursor,
                """
                INSERT INTO high_scores
                (date, fastest_burst_wpm, burst_duration_sec, burst_key_count,
                 timestamp, burst_duration_ms)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """,
                [
                    (
                        h["date"],
                        h["fastest_burst_wpm"],
                        h["burst_duration_sec"],
                        h["burst_key_count"],
                        h["timestamp"],
                        h.get("burst_duration_ms"),
                    )
                    for h in data["high_scores"]
                ],
            )
            log.info(f"Migrated {len(data['high_scores'])} high scores")

        # Migrate daily summaries
        log.info("Migrating daily summaries to PostgreSQL...")
        if data["daily_summaries"]:
            execute_batch(
                cursor,
                """
                INSERT INTO daily_summaries
                (date, total_keystrokes, total_bursts, avg_wpm,
                 slowest_keycode, slowest_key_name, total_typing_sec, summary_sent)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (date) DO UPDATE SET
                    total_keystrokes = EXCLUDED.total_keystrokes,
                    total_bursts = EXCLUDED.total_bursts,
                    avg_wpm = EXCLUDED.avg_wpm,
                    slowest_keycode = EXCLUDED.slowest_keycode,
                    slowest_key_name = EXCLUDED.slowest_key_name,
                    total_typing_sec = EXCLUDED.total_typing_sec,
                    summary_sent = EXCLUDED.summary_sent
            """,
                [
                    (
                        d["date"],
                        d["total_keystrokes"],
                        d["total_bursts"],
                        d["avg_wpm"],
                        d["slowest_keycode"],
                        d["slowest_key_name"],
                        d["total_typing_sec"],
                        d.get("summary_sent", 0),
                    )
                    for d in data["daily_summaries"]
                ],
            )
            log.info(f"Migrated {len(data['daily_summaries'])} daily summaries")

        # Migrate word statistics
        log.info("Migrating word statistics to PostgreSQL...")
        if data["word_statistics"]:
            execute_batch(
                cursor,
                """
                INSERT INTO word_statistics
                (word, layout, avg_speed_ms_per_letter, total_letters,
                 total_duration_ms, observation_count, last_seen,
                 backspace_count, editing_time_ms)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (word, layout) DO UPDATE SET
                    avg_speed_ms_per_letter = EXCLUDED.avg_speed_ms_per_letter,
                    total_letters = EXCLUDED.total_letters,
                    total_duration_ms = EXCLUDED.total_duration_ms,
                    observation_count = EXCLUDED.observation_count,
                    last_seen = EXCLUDED.last_seen,
                    backspace_count = EXCLUDED.backspace_count,
                    editing_time_ms = EXCLUDED.editing_time_ms
            """,
                [
                    (
                        w["word"],
                        w["layout"],
                        w["avg_speed_ms_per_letter"],
                        w["total_letters"],
                        w["total_duration_ms"],
                        w["observation_count"],
                        w["last_seen"],
                        w.get("backspace_count", 0),
                        w.get("editing_time_ms", 0),
                    )
                    for w in data["word_statistics"]
                ],
            )
            log.info(f"Migrated {len(data['word_statistics'])} word statistics")

        conn.commit()
        log.info("Migration completed successfully!")

    except Exception as e:
        conn.rollback()
        log.error(f"Migration failed: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


def main():
    """Main migration function."""
    # Get database path
    data_dir = Path.home() / ".local" / "share" / "realtypecoach"
    db_path = data_dir / "typing_data.db"

    if not db_path.exists():
        log.error(f"Database not found: {db_path}")
        sys.exit(1)

    log.info(f"Reading from: {db_path}")

    # Initialize crypto manager
    crypto = CryptoManager(db_path)

    # Read SQLite data
    data = get_sqlite_data(db_path, crypto)

    # Get PostgreSQL config from settings
    config_db_path = data_dir / "typing_data.db"
    config = Config(config_db_path)

    pg_host = config.get("postgres_host", "")
    pg_port = config.get_int("postgres_port", 5432)
    pg_database = config.get("postgres_database", "realtypecoach")
    pg_user = config.get("postgres_user", "")
    pg_password = crypto.get_postgres_password()

    if not all([pg_host, pg_database, pg_user, pg_password]):
        log.error("PostgreSQL configuration incomplete.")
        log.error("Please set the following in settings:")
        log.error("  - postgres_host")
        log.error("  - postgres_database")
        log.error("  - postgres_user")
        log.error("  - postgres_password (via keyring)")
        sys.exit(1)

    pg_config = {
        "host": pg_host,
        "port": pg_port,
        "database": pg_database,
        "user": pg_user,
        "password": pg_password,
        "sslmode": "require",
    }

    log.info(f"Migrating to PostgreSQL at {pg_host}:{pg_port}/{pg_database}")

    # Confirm migration
    total_records = sum(len(v) for v in data.values())
    print(f"\nAbout to migrate {total_records} records.")
    response = input("Continue? (yes/no): ")

    if response.lower() != "yes":
        log.info("Migration cancelled.")
        sys.exit(0)

    # Perform migration
    migrate_to_postgres(data, pg_config)

    log.info("All data migrated successfully!")
    log.info("You can now switch to PostgreSQL backend in settings.")


if __name__ == "__main__":
    main()
