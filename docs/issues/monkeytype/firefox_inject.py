#!/usr/bin/env python3
"""
Inject custom text into Firefox's localStorage for Monkeytype.

Firefox stores localStorage in SQLite, which Python can read/write natively!

Usage:
    python3 firefox_inject.py "Your text here"
    python3 firefox_inject.py --file text.txt
    python3 firefox_inject.py --profile PROFILE "text"
"""
import sys
import sqlite3
import json
import webbrowser
from pathlib import Path


def find_firefox_profiles():
    """Find all Firefox profiles."""
    firefox_dir = Path.home() / ".mozilla/firefox"

    if not firefox_dir.exists():
        return []

    profiles = []
    for path in firefox_dir.iterdir():
        if path.is_dir() and ".default" in path.name:
            # Try new localStorage format first (storage/default/https+++monkeytype.com/ls/data.sqlite)
            new_storage = path / "storage/default/https+++monkeytype.com/ls/data.sqlite"
            # Fall back to old format (webappsstore.sqlite)
            old_storage = path / "webappsstore.sqlite"

            if new_storage.exists():
                profiles.append({
                    "name": path.name,
                    "path": path,
                    "sqlite": new_storage,
                    "storage_type": "new"
                })
            elif old_storage.exists():
                profiles.append({
                    "name": path.name,
                    "path": path,
                    "sqlite": old_storage,
                    "storage_type": "old"
                })

    return profiles


def get_firefox_profile(profile_name=None):
    """Get a specific Firefox profile or the default one."""

    profiles = find_firefox_profiles()

    if not profiles:
        raise FileNotFoundError(
            "No Firefox profiles found. Make sure Firefox is installed and has been run."
        )

    if profile_name:
        for profile in profiles:
            if profile_name in profile["name"]:
                return profile
        raise FileNotFoundError(f"Profile '{profile_name}' not found")

    # Return the most recently used profile (largest file modification time)
    profiles.sort(key=lambda p: p["sqlite"].stat().st_mtime, reverse=True)
    return profiles[0]


def inject_text_to_firefox(text: str, mode: str = "repeat", profile_name=None):
    """Inject custom text into Firefox's localStorage for monkeytype.com."""

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

    # Get the profile
    profile = get_firefox_profile(profile_name)

    print(f"📁 Using Firefox profile: {profile['name']}")
    print(f"   Database: {profile['sqlite']}")
    print(f"   Storage type: {profile.get('storage_type', 'old')}")

    # Open the database
    conn = sqlite3.connect(str(profile["sqlite"]))
    cursor = conn.cursor()

    try:
        json_value = json.dumps(custom_text_settings)
        storage_type = profile.get('storage_type', 'old')

        if storage_type == 'new':
            # New Firefox localStorage format (storage/default/https+++monkeytype.com/ls/data.sqlite)

            # Set mode to custom in config (delete existing and insert uncompressed)
            cursor.execute('DELETE FROM data WHERE key = ?', ('config',))
            config = {"mode": "custom", "punctuation": False, "numbers": False, "time": 30}
            config_json = json.dumps(config)
            cursor.execute(
                'INSERT INTO data (key, utf16_length, conversion_type, compression_type, last_access_time, value) VALUES (?, ?, ?, ?, ?, ?)',
                ('config', len(config_json) * 2, 1, 0, 0, config_json)
            )
            print(f"\n📝 Config set to mode: custom")

            # Inject custom text
            cursor.execute('SELECT value FROM data WHERE key = ?', ('customTextSettings',))
            existing = cursor.fetchone()

            if existing:
                print(f"\n📝 Found existing custom text, replacing with new text...")
                cursor.execute('UPDATE data SET value = ?, utf16_length = ? WHERE key = ?',
                              (json_value, len(json_value) * 2, 'customTextSettings'))
            else:
                cursor.execute(
                    'INSERT INTO data (key, utf16_length, conversion_type, compression_type, last_access_time, value) VALUES (?, ?, ?, ?, ?, ?)',
                    ('customTextSettings', len(json_value) * 2, 0, 0, 0, json_value)
                )

            # Set customTextName and customTextLong (required by Monkeytype)
            import time
            text_name = f"rtc_{int(time.time() * 1000)}"
            cursor.execute('DELETE FROM data WHERE key = ?', ('customTextName',))
            cursor.execute(
                'INSERT INTO data (key, utf16_length, conversion_type, compression_type, last_access_time, value) VALUES (?, ?, ?, ?, ?, ?)',
                ('customTextName', len(text_name) * 2, 0, 0, 0, text_name)
            )

            cursor.execute('DELETE FROM data WHERE key = ?', ('customTextLong',))
            cursor.execute(
                'INSERT INTO data (key, utf16_length, conversion_type, compression_type, last_access_time, value) VALUES (?, ?, ?, ?, ?, ?)',
                ('customTextLong', 10, 0, 0, 0, 'false')
            )

            # Also save to customText (saved texts collection)
            custom_text = {text_name: text}
            custom_text_json = json.dumps(custom_text)
            cursor.execute('DELETE FROM data WHERE key = ?', ('customText',))
            cursor.execute(
                'INSERT INTO data (key, utf16_length, conversion_type, compression_type, last_access_time, value) VALUES (?, ?, ?, ?, ?, ?)',
                ('customText', len(custom_text_json) * 2, 0, 0, 0, custom_text_json)
            )
        else:
            # Old Firefox localStorage format (webappsstore.sqlite)
            cursor.execute(
                "SELECT value FROM webappsstore2 WHERE scope = ? AND key = ?",
                ("https://monkeytype.com", "customTextSettings")
            )
            existing = cursor.fetchone()

            if existing:
                existing_value = json.loads(existing[0])
                print(f"\n📝 Found existing custom text:")
                print(f"   - Words: {len(existing_value.get('text', []))}")
                print(f"   - Mode: {existing_value.get('mode', 'unknown')}")
                print(f"\n   Replacing with new text...")

            # First try to update
            cursor.execute(
                """UPDATE webappsstore2
                   SET value = ?
                   WHERE scope = ? AND key = ?""",
                (json_value, "https://monkeytype.com", "customTextSettings")
            )

            # If no rows were updated, do an insert
            if cursor.rowcount == 0:
                cursor.execute(
                    """INSERT INTO webappsstore2
                       (originAttributes, originKey, scope, key, value)
                       VALUES (?, ?, ?, ?, ?)""",
                    ("", "https://monkeytype.com", "https://monkeytype.com", "customTextSettings", json_value)
                )

        conn.commit()

        print(f"\n✅ Successfully injected text into Firefox's localStorage!")
        print(f"   - Words: {len(words)}")
        print(f"   - Characters: {len(text)}")
        print(f"   - Mode: {mode}")

    finally:
        conn.close()

    # Close Firefox first to ensure fresh load
    print(f"\n🔄 Closing Firefox to ensure fresh load...")
    import subprocess
    subprocess.run(["killall", "firefox"], stderr=subprocess.DEVNULL, timeout=5)
    import time
    time.sleep(2)  # Wait for Firefox to fully close

    # Open Firefox to monkeytype.com in a private window (single tab, no session restore)
    print(f"✨ Opening Firefox to monkeytype.com...")
    print("="*60)
    subprocess.Popen(["firefox", "--private-window", "https://monkeytype.com"])


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
        print("\nOptions:")
        print("  --file FILE      Read text from file")
        print("  --mode MODE      Mode: repeat, zip, maximize")
        print("  --profile NAME   Use specific Firefox profile")
        print("  --list-profiles  List all Firefox profiles")
        sys.exit(1)

    mode = "repeat"
    profile_name = None
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
        elif arg == "--profile":
            if i + 1 >= len(sys.argv):
                print("Error: --profile requires profile name")
                sys.exit(1)
            profile_name = sys.argv[i + 1]
            i += 2
        elif arg == "--list-profiles":
            profiles = find_firefox_profiles()
            print("Available Firefox profiles:")
            for p in profiles:
                print(f"  - {p['name']}")
            sys.exit(0)
        elif arg.startswith("--"):
            print(f"Unknown option: {arg}")
            sys.exit(1)
        else:
            text = ' '.join(sys.argv[i:])
            break

    if not text:
        print("Error: No text provided")
        sys.exit(1)

    try:
        inject_text_to_firefox(text, mode, profile_name)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
