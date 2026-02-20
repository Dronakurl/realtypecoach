#!/usr/bin/env python3
"""
Open Monkeytype with custom text for practicing difficult words.

This script creates a marker file that the Tampermonkey userscript reads.
Then opens your default browser to Monkeytype.

Usage:
    python3 open_monkeytype_with_text.py "Your text here"
    python3 open_monkeytype_with_text.py --file text.txt

Installation (one-time setup):
    1. Install Tampermonkey on your browser
    2. Open monkeytype_autoinject.user.js in Tampermonkey
    3. Save the script
    4. That's it! Now this script will work automatically.
"""

import json
import sys
import time
import webbrowser
from pathlib import Path

RTC_TEXT_FILE = Path.home() / ".rtc_monkeytype_text.txt"


def set_injection_text(text: str):
    """Set the text to be injected into Monkeytype."""
    print(f"📝 Text to inject ({len(text)} chars): {text[:60]}{'...' if len(text) > 60 else ''}")

    # Write to file that Tampermonkey will read
    data = {"text": text, "timestamp": int(time.time() * 1000)}

    RTC_TEXT_FILE.write_text(json.dumps(data))
    print("✅ Text file created for Tampermonkey")

    return RTC_TEXT_FILE


def open_monkeytype():
    """Open browser with Monkeytype."""
    print("🌐 Opening Monkeytype in your default browser...")
    print("=" * 60)
    print("The Tampermonkey script will auto-inject your text!")
    print("=" * 60)

    webbrowser.open("https://monkeytype.com")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nError: No text provided")
        sys.exit(1)

    if sys.argv[1] == "--file":
        if len(sys.argv) < 3:
            print("Error: --file requires a filepath")
            sys.exit(1)
        text = Path(sys.argv[2]).read_text()
    else:
        text = " ".join(sys.argv[1:])

    try:
        set_injection_text(text)
        time.sleep(0.5)  # Give the file time to be written
        open_monkeytype()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
