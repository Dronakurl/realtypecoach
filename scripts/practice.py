#!/usr/bin/env python3
"""
Launch a browser-based typing practice session with custom text.

Usage:
    python3 practice.py "Your practice text here"
    python3 practice.py --file path/to/text.txt
    python3 practice.py --clipboard  # Use text from clipboard
"""
import sys
import webbrowser
import urllib.parse
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
HTML_FILE = SCRIPT_DIR / "typing_practice.html"


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


def launch_practice(text: str):
    """Launch browser with typing practice and the given text."""
    # Truncate text if too long (URL limits)
    if len(text) > 5000:
        print(f"Warning: Text is {len(text)} chars, truncating to 5000")
        text = text[:5000]

    # Create file URL with encoded text parameter
    file_url = HTML_FILE.as_uri()
    full_url = f"{file_url}?text={urllib.parse.quote(text)}"

    print(f"Opening typing practice with {len(text)} characters...")
    print("Press Tab to restart, Esc to close browser tab")
    webbrowser.open(full_url)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    if sys.argv[1] == '--file':
        if len(sys.argv) < 3:
            print("Error: --file requires a filepath argument")
            sys.exit(1)
        text = get_text_from_file(sys.argv[2])

    elif sys.argv[1] == '--clipboard':
        text = get_text_from_clipboard()
        if not text:
            print("Error: Clipboard is empty")
            sys.exit(1)

    else:
        # Treat all arguments as the practice text
        text = ' '.join(sys.argv[1:])

    launch_practice(text)


if __name__ == '__main__':
    main()
