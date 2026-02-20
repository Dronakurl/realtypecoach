#!/usr/bin/env python3
"""
Inject custom text into Monkeytype (online or local).

This opens a helper page that provides the injection code and instructions.

Usage:
    python3 monkeytype_inject.py "Your text here"
    python3 monkeytype_inject.py --file text.txt
    python3 monkeytype_inject.py --mode zip "text"
"""

import sys
import urllib.parse
import webbrowser
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
INJECTOR_HTML = SCRIPT_DIR / "monkeytype_auto_inject.html"


def get_text_from_clipboard() -> str:
    """Get text from clipboard."""
    try:
        import pyperclip

        return pyperclip.paste()
    except ImportError:
        print("Error: pyperclip not installed. Install with: pip install pyperclip")
        sys.exit(1)


def get_text_from_file(filepath: str) -> str:
    """Read text from file."""
    path = Path(filepath)
    if not path.exists():
        print(f"Error: File not found: {filepath}")
        sys.exit(1)
    return path.read_text()


def launch_injector(text: str, mode: str = "repeat"):
    """Launch the injector helper page."""

    # Truncate if too long
    if len(text) > 5000:
        print(f"Warning: Text is {len(text)} chars, truncating to 5000")
        text = text[:5000]

    # Build URL with parameters
    file_url = INJECTOR_HTML.as_uri()
    params = {"text": text, "mode": mode}

    query_string = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    full_url = f"{file_url}?{query_string}"

    word_count = len(text.split())
    print("🐵 Opening Monkeytype injector...")
    print(f"   Text: {word_count} words, {len(text)} characters")
    print(f"   Mode: {mode}")
    print()
    print("Follow the instructions on the page:")
    print("  1. Copy the injection code")
    print("  2. Open Monkeytype (click the button)")
    print("  3. Paste code into browser console (F12 → Console)")
    print()

    webbrowser.open(full_url)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nModes: repeat, zip, maximize")
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
        elif arg == "--clipboard":
            text = get_text_from_clipboard()
            if not text:
                print("Error: Clipboard is empty")
                sys.exit(1)
            i += 1
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
            text = " ".join(sys.argv[i:])
            break

    if not text:
        print("Error: No text provided")
        sys.exit(1)

    launch_injector(text, mode)


if __name__ == "__main__":
    main()
