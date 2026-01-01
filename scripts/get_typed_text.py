#!/usr/bin/env python3
"""Retrieve and reconstruct typed text from keystroke history."""

import argparse
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.storage import Storage
from core.dictionary_config import DictionaryConfig
from utils.config import Config
from utils.crypto import CryptoManager
import sqlcipher3 as sqlite3


def get_typed_text(limit: int = -1) -> str:
    """Reconstruct typed text from keystroke database.

    Args:
        limit: Maximum number of characters to retrieve (-1 for all)

    Returns:
        Reconstructed typed text
    """
    db_path = Path.home() / '.local' / 'share' / 'realtypecoach' / 'typing_data.db'

    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        sys.exit(1)

    # Initialize crypto manager
    crypto = CryptoManager(db_path)
    key = crypto.get_key()

    # Connect to database
    conn = sqlite3.connect(db_path)
    conn.execute(f"PRAGMA key = \"x'{key.hex()}'\"")
    cursor = conn.cursor()

    # Get all key events ordered by timestamp
    cursor.execute("""
        SELECT timestamp_ms, keycode, key_name, event_type
        FROM key_events
        ORDER BY timestamp_ms ASC
    """)

    events = cursor.fetchall()
    conn.close()

    if not events:
        return ""

    # Reconstruct text
    text_parts = []
    char_count = 0

    # Map special keycodes to their character representations
    special_chars = {
        28: "\n",  # ENTER -> newline
        57: " ",   # SPACE -> space
    }

    # Control keys to ignore (not printable)
    control_keycodes = {
        1,   # ESC
        14,  # BACKSPACE
        15,  # TAB
        29,  # LEFT_CTRL
        42,  # LEFT_SHIFT
        54,  # RIGHT_SHIFT
        56,  # LEFT_ALT
        58,  # CAPS_LOCK
        97,  # RIGHT_CTRL
        100, # RIGHT_ALT
        102, # HOME
        103, # UP
        104, # PAGE_UP
        105, # LEFT
        106, # RIGHT
        107, # END
        108, # DOWN
        109, # PAGE_DOWN
        110, # INSERT
        111, # DELETE
        127, # PAUSE
        # F-keys
        59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 87, 88,
        # Keypad
        69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 98, 99,
    }

    # Printable keycodes - letters (q=16 through p=25, a=30 through l=38, z=44 through m=50)
    printable_keycodes = {
        # Letters - top row
        16, 17, 18, 19, 20, 21, 22, 23, 24, 25,  # q w e r t y u i o p
        # Letters - middle row
        30, 31, 32, 33, 34, 35, 36, 37, 38,  # a s d f g h j k l
        # Letters - bottom row
        44, 45, 46, 47, 48, 49, 50,  # z x c v b n m
        # Numbers
        2, 3, 4, 5, 6, 7, 8, 9, 10, 11,  # 1-9 and 0
        # Punctuation and symbols
        12,  # minus
        13,  # equals
        26,  # opening bracket
        27,  # closing bracket
        39,  # semicolon
        40,  # apostrophe
        41,  # backtick
        43,  # backslash
        51,  # comma
        52,  # period
        53,  # slash
    }

    # Process events (reconstruct all text first)
    for event in events:
        timestamp_ms, keycode, key_name, event_type = event

        # Only process press events
        if event_type != "press":
            continue

        # Skip control keys
        if keycode in control_keycodes:
            continue

        if keycode in special_chars:
            # Use special character mapping
            text_parts.append(special_chars[keycode])
            char_count += 1
        elif keycode in printable_keycodes and key_name:
            # Add the character
            text_parts.append(key_name)
            char_count += 1

    # Join all text
    full_text = "".join(text_parts)

    # Return last N characters if limit is specified
    if limit != -1 and limit < len(full_text):
        return full_text[-limit:]

    return full_text


def main():
    parser = argparse.ArgumentParser(
        description="Retrieve and reconstruct typed text from keystroke history"
    )
    parser.add_argument(
        "limit",
        nargs="?",
        type=int,
        default=-1,
        help="Maximum number of characters to retrieve (default: -1 for all)",
    )

    args = parser.parse_args()

    try:
        text = get_typed_text(args.limit)
        print(text)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
