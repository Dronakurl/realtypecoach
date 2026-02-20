#!/usr/bin/env python3
"""
Inject custom text into ALL Firefox profiles for Monkeytype.

Usage:
    python3 firefox_inject_all.py "Your text here"
"""

import json
import sqlite3
import subprocess
import sys
import time
import webbrowser
from pathlib import Path


def find_firefox_profiles():
    """Find all Firefox profiles."""
    firefox_dir = Path.home() / ".mozilla/firefox"
    profiles = []

    for path in firefox_dir.iterdir():
        if path.is_dir() and ".default" in path.name:
            sqlite_path = path / "webappsstore.sqlite"
            if sqlite_path.exists():
                profiles.append({"name": path.name, "path": path, "sqlite": sqlite_path})

    return profiles


def inject_text(text: str, mode: str = "repeat"):
    """Inject text into all Firefox profiles."""

    words = text.split()

    custom_text_settings = {
        "text": words,
        "mode": mode,
        "limit": {"value": len(words), "mode": "word"},
        "pipeDelimiter": False,
    }

    json_value = json.dumps(custom_text_settings)

    profiles = find_firefox_profiles()

    print(f"Found {len(profiles)} Firefox profile(s)")

    # Close Firefox first
    print("Closing Firefox...")
    subprocess.run(["killall", "firefox"], stderr=subprocess.DEVNULL)
    time.sleep(2)

    # Inject into each profile
    for profile in profiles:
        print(f"\n📁 Injecting into profile: {profile['name']}")

        try:
            conn = sqlite3.connect(str(profile["sqlite"]))
            cursor = conn.cursor()

            # Update or insert
            cursor.execute(
                """UPDATE webappsstore2
                   SET value = ?
                   WHERE scope = ? AND key = ?""",
                (json_value, "https://monkeytype.com", "customTextSettings"),
            )

            if cursor.rowcount == 0:
                cursor.execute(
                    """INSERT INTO webappsstore2
                       (originAttributes, originKey, scope, key, value)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        "",
                        "https://monkeytype.com",
                        "https://monkeytype.com",
                        "customTextSettings",
                        json_value,
                    ),
                )

            conn.commit()
            conn.close()
            print("   ✓ Success")

        except Exception as e:
            print(f"   ✗ Error: {e}")

    # Open Firefox
    print("\n✨ Opening Firefox...")
    print("=" * 60)
    webbrowser.get("firefox").open("https://monkeytype.com")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    text = " ".join(sys.argv[1:])
    inject_text(text)


if __name__ == "__main__":
    main()
