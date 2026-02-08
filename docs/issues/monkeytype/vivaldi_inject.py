#!/usr/bin/env python3
"""
Directly inject custom text into Vivaldi's localStorage for Monkeytype.

This script manipulates Vivaldi's leveldb files directly.

Usage:
    python3 vivaldi_inject.py "Your text here"
    python3 vivaldi_inject.py --file text.txt
"""
import sys
import json
from pathlib import Path

try:
    import plyvel
except ImportError:
    print("Error: plyvel not installed.")
    print("Install with: pip install plyvel")
    sys.exit(1)


def get_vivaldi_leveldb_path():
    """Find Vivaldi's localStorage leveldb path."""

    possible_paths = [
        Path.home() / ".config/vivaldi/Default/Local Storage/leveldb",
        Path.home() / ".config/vivaldi/Default/Storage/ext/mpognobbkildjkofajifpdfhcoklimli/def/Local Storage/leveldb",
    ]

    for path in possible_paths:
        if path.exists() and (path / "CURRENT").exists():
            return path

    raise FileNotFoundError(
        "Could not find Vivaldi's localStorage leveldb.\n"
        "Make sure Vivaldi is installed and has been run at least once."
    )


def inject_text_to_vivaldi(text: str, mode: str = "repeat"):
    """
    Inject custom text into Vivaldi's localStorage for monkeytype.com.
    """

    # Split text into words
    words = text.split()

    # Create the customTextSettings object
    custom_text_settings = {
        "text": words,
        "mode": mode,
        "limit": {
            "value": len(words),
            "mode": "word"
        },
        "pipeDelimiter": False
    }

    # Get leveldb path
    leveldb_path = get_vivaldi_leveldb_path()
    print(f"📁 Found Vivaldi storage at: {leveldb_path}")

    # Open leveldb (read-only first to check)
    try:
        db = plyvel.DB(str(leveldb_path), create_if_missing=False, write_buffer_size=16*1024*1024)
    except Exception as e:
        print(f"❌ Error opening leveldb: {e}")
        print("\n💡 Make sure Vivaldi is CLOSED before running this script!")
        sys.exit(1)

    try:
        # Look for monkeytype.com keys
        monkeytype_key_prefix = b"_https://monkeytype.com\x00"
        existing_key = None

        print("🔍 Searching for Monkeytype data...")

        # Scan for existing keys
        for key, value in db.iterator(prefix=monkeytype_key_prefix):
            key_str = key.decode('utf-8', errors='ignore')
            if 'customTextSettings' in key_str:
                existing_key = key
                existing_value = json.loads(value.decode('utf-8'))
                print(f"   Found existing customTextSettings:")
                print(f"   - Words: {len(existing_value.get('text', []))}")
                print(f"   - Mode: {existing_value.get('mode', 'unknown')}")
                break

        # Create the key for customTextSettings
        # Format: _https://monkeytype.com\x00\x01customTextSettings
        new_key = b"_https://monkeytype.com\x00\x01customTextSettings"
        new_value = json.dumps(custom_text_settings).encode('utf-8')

        print(f"\n📝 Injecting new text:")
        print(f"   - Words: {len(words)}")
        print(f"   - Characters: {len(text)}")
        print(f"   - Mode: {mode}")

        # Close and reopen with write permissions
        db.close()

        # For leveldb, we need to use a write batch and handle the locking properly
        # Vivaldi locks the DB when running, so we need to be careful
        try:
            # Try to open with write permissions
            db = plyvel.DB(str(leveldb_path), create_if_missing=False, write_buffer_size=16*1024*1024)

            # Write the new value
            db.put(new_key, new_value)

            print(f"\n✅ Successfully injected text into Vivaldi's localStorage!")

            # Verify
            stored_value = db.get(new_key)
            if stored_value:
                stored_json = json.loads(stored_value.decode('utf-8'))
                if stored_json['text'] == words:
                    print("✅ Verification successful!")
                else:
                    print("⚠️  Warning: Stored value doesn't match!")

            db.close()

        except Exception as e:
            print(f"❌ Error writing to database: {e}")
            print("\n💡 Make sure Vivaldi is CLOSED!")
            sys.exit(1)

    finally:
        if 'db' in locals():
            db.close()

    print("\n" + "="*60)
    print("✨ Next steps:")
    print("   1. Open Vivaldi")
    print("   2. Go to https://monkeytype.com")
    print("   3. Your custom text should be active!")
    print("="*60)


def get_text_from_file(filepath: str) -> str:
    """Read text from file."""
    path = Path(filepath)
    if not path.exists():
        print(f"Error: File not found: {filepath}")
        sys.exit(1)
    return path.read_text()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nModes: repeat, zip, maximize")
        print("\n⚠️  IMPORTANT: Close Vivaldi before running this script!")
        sys.exit(1)

    mode = "repeat"
    text = None

    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]

        if arg == "--file":
            if i + 1 >= len(sys.argv):
                print("Error: --file requires filepath")
                sys.exit(1)
            text = get_text_from_file(sys.argv[i + 1])
            i += 2
        elif arg == "--mode":
            if i + 1 >= len(sys.argv):
                print("Error: --mode requires mode name")
                sys.exit(1)
            mode = sys.argv[i + 1]
            i += 2
        elif arg.startswith("--"):
            print(f"Unknown option: {arg}")
            sys.exit(1)
        else:
            text = ' '.join(sys.argv[i:])
            break

    if not text:
        print("Error: No text provided")
        sys.exit(1)

    print("⚠️  Make sure Vivaldi is CLOSED before continuing!")
    print("   Press Ctrl+C to cancel, or wait 3 seconds...")
    import time
    try:
        time.sleep(3)
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(0)

    try:
        inject_text_to_vivaldi(text, mode)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
