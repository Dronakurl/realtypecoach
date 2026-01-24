#!/usr/bin/env python3
"""Ad-hoc query tool for RealTypeCoach encrypted database.

Usage:
    python scripts/db_query.py "SELECT * FROM bursts LIMIT 10"
    python scripts/db_query.py --schema
    python scripts/db_query.py --table bursts
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime

import sqlcipher3 as sqlite3

from utils.crypto import CryptoManager

# Get database path
db_path = Path.home() / ".local" / "share" / "realtypecoach" / "typing_data.db"

if not db_path.exists():
    print(f"Error: Database not found at {db_path}")
    sys.exit(1)


def get_connection():
    """Get encrypted database connection."""
    crypto = CryptoManager(db_path)
    key = crypto.get_key()

    if not key:
        print("Error: No encryption key found in keyring")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.execute(f"PRAGMA key = \"x'{key.hex()}'\"")

    return conn


def print_schema(conn):
    """Print database schema."""
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = cursor.fetchall()

    print("Database Schema:")
    print("=" * 80)

    for (table_name,) in tables:
        print(f"\nTable: {table_name}")
        print("-" * 40)

        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = cursor.fetchall()

        print(f"{'Column':<30} {'Type':<15} {'Nullable'}")
        print("-" * 60)

        for col in columns:
            cid, name, type_, notnull, default, pk = col
            nullable = "NOT NULL" if notnull else "NULL"
            pk_str = " (PK)" if pk else ""
            print(f"{name:<30} {type_:<15} {nullable}{pk_str}")


def print_table(conn, table_name, limit=10):
    """Print table contents."""
    cursor = conn.cursor()

    # Get column info
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    col_names = [col[1] for col in columns]

    # Get row count
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    total_rows = cursor.fetchone()[0]

    # Get data
    cursor.execute(f"SELECT * FROM {table_name} ORDER BY rowid DESC LIMIT {limit}")
    rows = cursor.fetchall()

    print(f"\nTable: {table_name} (showing {len(rows)} of {total_rows} rows)")
    print("=" * 80)

    # Print header
    print(" | ".join(col_names))
    print("-" * 80)

    # Print rows
    for row in rows:
        formatted = []
        for i, val in enumerate(row):
            col_type = columns[i][2]
            if col_type == "INTEGER" and val and "time" in col_names[i].lower():
                # Format timestamps
                try:
                    if isinstance(val, (int, float)) and val > 1000000000000:
                        # Millisecond timestamp
                        formatted.append(
                            datetime.fromtimestamp(val / 1000).strftime("%Y-%m-%d %H:%M:%S")
                        )
                    elif isinstance(val, (int, float)) and val > 1000000000:
                        # Second timestamp
                        formatted.append(datetime.fromtimestamp(val).strftime("%Y-%m-%d %H:%M:%S"))
                    else:
                        formatted.append(str(val))
                except (ValueError, OSError):
                    formatted.append(str(val))
            else:
                formatted.append(str(val)[:30])  # Truncate long values

        print(" | ".join(formatted))


def execute_query(conn, query, limit=None):
    """Execute SQL query and print results."""
    cursor = conn.cursor()

    # Add limit if specified
    if limit and "LIMIT" not in query.upper():
        query = f"{query} LIMIT {limit}"

    try:
        cursor.execute(query)

        # Check if query returns data
        if cursor.description:
            # Get column names
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()

            print(f"\nQuery Results ({len(rows)} rows):")
            print("=" * 80)
            print(" | ".join(columns))
            print("-" * 80)

            for row in rows:
                formatted = []
                for val in row:
                    # Format timestamps
                    if isinstance(val, (int, float)) and val > 1000000000000:
                        try:
                            formatted.append(
                                datetime.fromtimestamp(val / 1000).strftime("%Y-%m-%d %H:%M:%S")
                            )
                        except (ValueError, OSError):
                            formatted.append(str(val))
                    elif isinstance(val, (int, float)) and val > 1000000000:
                        try:
                            formatted.append(
                                datetime.fromtimestamp(val).strftime("%Y-%m-%d %H:%M:%S")
                            )
                        except (ValueError, OSError):
                            formatted.append(str(val))
                    else:
                        formatted.append(str(val)[:50] if val else "NULL")

                print(" | ".join(formatted))

            # Print row count
            print(f"\nTotal: {len(rows)} rows")

        else:
            # INSERT, UPDATE, DELETE, etc.
            conn.commit()
            print(f"Query executed successfully. {cursor.rowcount} rows affected.")

    except sqlite3.Error as e:
        print(f"Error executing query: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Query RealTypeCoach encrypted database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "SELECT * FROM bursts LIMIT 10"
  %(prog)s "SELECT avg_wpm, duration_ms FROM bursts WHERE avg_wpm > 40"
  %(prog)s --schema
  %(prog)s --table bursts
  %(prog)s --table bursts --limit 20
        """,
    )

    parser.add_argument("query", nargs="?", help="SQL query to execute")
    parser.add_argument("--schema", action="store_true", help="Show database schema")
    parser.add_argument("--table", metavar="NAME", help="Show contents of a table")
    parser.add_argument(
        "--limit", type=int, default=10, help="Limit rows for --table (default: 10)"
    )

    args = parser.parse_args()

    conn = get_connection()

    try:
        if args.schema:
            print_schema(conn)
        elif args.table:
            print_table(conn, args.table, args.limit)
        elif args.query:
            execute_query(conn, args.query, limit=None)
        else:
            # Default: show recent bursts
            print("Recent bursts (last 10):")
            execute_query(
                conn,
                """
                SELECT burst_id, start_time, key_count, backspace_count, net_key_count,
                       duration_ms, avg_wpm
                FROM bursts
                ORDER BY start_time DESC
                LIMIT 10
                """,
            )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
