#!/usr/bin/env python3
"""Manually sync local SQLite with remote PostgreSQL.

Usage:
    python scripts/sync.py
    python scripts/sync.py --verbose
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.storage import Storage
from utils.config import Config


def setup_logging(verbose: bool = False) -> None:
    """Setup logging for sync script."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main():
    parser = argparse.ArgumentParser(
        description="Manually sync local SQLite with remote PostgreSQL",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s
  %(prog)s --verbose
        """,
    )

    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging"
    )

    args = parser.parse_args()

    setup_logging(args.verbose)
    log = logging.getLogger("realtypecoach.sync_script")

    # Get database path
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

    # Check if PostgreSQL sync is enabled
    if not config.get_bool("postgres_sync_enabled", False):
        print("PostgreSQL sync is not enabled in config")
        sys.exit(1)

    # Initialize storage
    try:
        storage = Storage(db_path, config)
    except Exception as e:
        print(f"Error initializing storage: {e}")
        sys.exit(1)

    # Perform sync
    print("=" * 70)
    print("Starting sync...")
    print("=" * 70)

    start_time = datetime.now()

    try:
        result = storage.merge_with_remote()

        duration = (datetime.now() - start_time).total_seconds()

        print()
        print("=" * 70)
        if result["success"]:
            total_records = result["pushed"] + result["pulled"]
            print(f"✓ Sync completed successfully in {duration:.2f}s")
            print(f"  Pushed: {result['pushed']} records")
            print(f"  Pulled: {result['pulled']} records")
            print(f"  Conflicts resolved: {result['conflicts_resolved']}")
            print(f"  Total records transferred: {total_records}")
        else:
            print(f"✗ Sync failed")
            print(f"  Error: {result.get('error', 'Unknown error')}")
        print("=" * 70)

        sys.exit(0 if result["success"] else 1)

    except Exception as e:
        print()
        print("=" * 70)
        print(f"✗ Sync failed with exception")
        print(f"  Error: {e}")
        print("=" * 70)
        sys.exit(1)


if __name__ == "__main__":
    main()
