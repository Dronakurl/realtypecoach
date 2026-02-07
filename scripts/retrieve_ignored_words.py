#!/usr/bin/env python3
"""Retrieve ignored words hashes from the database.

This script attempts to retrieve the ignored words list. Since the system
uses one-way hashing (BLAKE2b-256 with pepper + user salt), we cannot directly
decrypt the hashes. However, we can:

1. Display all stored hashes
2. If you provide a wordlist, we can check which words match the hashes
3. Attempt a dictionary attack if you have candidate words

Usage:
    # Just show the hashes
    python scripts/retrieve_ignored_words.py

    # Check against a wordlist (one word per line)
    python scripts/retrieve_ignored_words.py --wordlist words.txt
"""

import argparse
import hashlib
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import sqlcipher3 as sqlite3  # noqa: E402

from utils.crypto import CryptoManager  # noqa: E402

# The hardcoded pepper from hash_manager.py
PEPPER = bytes.fromhex("1a2b3c4d5e6f1a2b3c4d5e6f1a2b3c4d5e6f1a2b3c4d5e6f1a2b3c4d5e6f1a2b")


def derive_user_salt(encryption_key: bytes) -> bytes:
    """Derive user_salt from encryption key (matches hash_manager.py)."""
    h = hashlib.blake2b(digest_size=32)
    h.update(encryption_key)
    h.update(b"ignored_words_user_salt_derivation")
    return h.digest()


def hash_word(word: str, encryption_key: bytes) -> str:
    """Hash a word using the same algorithm as hash_manager.py."""
    user_salt = derive_user_salt(encryption_key)
    word_normalized = word.lower().encode("utf-8")

    h = hashlib.blake2b(key=PEPPER, digest_size=32)
    h.update(user_salt)
    h.update(word_normalized)

    return h.hexdigest()


def get_db_path() -> Path:
    """Get the database path."""
    return Path.home() / ".local" / "share" / "realtypecoach" / "typing_data.db"


def get_db_connection(db_path: Path):
    """Get encrypted database connection."""
    crypto = CryptoManager(db_path)
    key = crypto.get_key()

    if not key:
        print("Error: No encryption key found in keyring")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.execute(f"PRAGMA key = \"x'{key.hex()}'\"")
    return conn


def get_ignored_hashes(conn) -> list[tuple[str, int]]:
    """Retrieve all ignored word hashes from the database."""
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT word_hash, added_at FROM ignored_words ORDER BY added_at DESC")
        return cursor.fetchall()
    except sqlite3.OperationalError:
        print("Note: ignored_words table doesn't exist in the database")
        return []


def get_encryption_key(db_path: Path) -> bytes | None:
    """Get the encryption key from CryptoManager."""
    crypto = CryptoManager(db_path)
    return crypto.get_key()


def check_wordlist(hashes: list[str], wordlist_path: Path, encryption_key: bytes) -> dict:
    """Check which words from wordlist match the stored hashes."""
    hash_set = set(hashes)
    matches = {}

    print(f"Checking {wordlist_path} against {len(hashes)} hashes...")

    with open(wordlist_path) as f:
        for line_num, line in enumerate(f, 1):
            word = line.strip()
            if not word:
                continue

            word_hash = hash_word(word, encryption_key)
            if word_hash in hash_set:
                matches[word] = word_hash
                print(f"  MATCH: '{word}' -> {word_hash[:16]}...")

    return matches


def main():
    parser = argparse.ArgumentParser(
        description="Retrieve ignored words from RealTypeCoach database"
    )
    parser.add_argument("--wordlist", "-w", type=Path, help="Check hashes against a wordlist file")
    parser.add_argument("--db", type=Path, help="Path to database file")
    args = parser.parse_args()

    # Get database path
    db_path = args.db if args.db else get_db_path()

    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        sys.exit(1)

    print(f"Using database: {db_path}\n")

    # Get encryption key and connection
    conn = None
    try:
        conn = get_db_connection(db_path)
    except Exception as e:
        print(f"Error: Could not open encrypted database: {e}")
        sys.exit(1)

    # Get encryption key for hashing
    crypto = CryptoManager(db_path)
    encryption_key = crypto.get_key()

    if encryption_key is None:
        print("Error: No encryption key found in keyring")
        sys.exit(1)

    print(f"Encryption key: {'✓ Found (' + len(encryption_key) * '•' + ')'}")
    user_salt = derive_user_salt(encryption_key)
    print(f"User salt derived: {user_salt.hex()[:32]}...")
    print()

    # Get ignored hashes
    ignored_data = get_ignored_hashes(conn)

    if not ignored_data:
        print("No ignored words found in database.")
        return

    hashes = [h[0] for h in ignored_data]
    print(f"Found {len(hashes)} ignored word(s):\n")

    for word_hash, added_at in ignored_data:
        from datetime import datetime

        added_dt = datetime.fromtimestamp(added_at / 1000)
        print(f"  Hash: {word_hash}")
        print(f"    Added: {added_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        print()

    # If wordlist provided, try to find matches
    if args.wordlist:
        if not args.wordlist.exists():
            print(f"Error: Wordlist not found at {args.wordlist}")
            sys.exit(1)

        print("\n" + "=" * 60)
        print("Checking wordlist for matches...")
        print("=" * 60 + "\n")

        matches = check_wordlist(hashes, args.wordlist, encryption_key)

        print("\n" + "=" * 60)
        print(f"Found {len(matches)} matching word(s) out of {len(hashes)} total hashes")
        print("=" * 60 + "\n")

        if matches:
            print("Matched words:")
            for word, word_hash in matches.items():
                print(f"  - {word}")
    else:
        print("\nTip: Use --wordlist to check these hashes against a dictionary.")
        print("  Example: python scripts/retrieve_ignored_words.py -w /usr/share/dict/words")
        print("\nOr if you have a guess at what words might be ignored,")
        print("create a text file with one word per line and check it.")

    conn.close()


if __name__ == "__main__":
    main()
