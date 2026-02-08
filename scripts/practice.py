#!/usr/bin/env python3
"""
Launch typing practice session with custom text.

Opens the standalone typing practice page in your default browser.

Usage:
    python3 practice.py "Your practice text here"
    python3 practice.py --file path/to/text.txt
"""
import sys
import webbrowser
import urllib.parse
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
HTML_FILE = SCRIPT_DIR / "typing_practice.html"


def get_text_from_file(filepath: str) -> str:
    """Read text from file."""
    path = Path(filepath)
    if not path.exists():
        print(f"Error: File not found: {filepath}")
        sys.exit(1)
    return path.read_text()


def launch_practice(text: str):
    """Launch typing practice in default browser."""
    # Truncate text if too long (URL limits)
    if len(text) > 5000:
        print(f"Warning: Text is {len(text)} chars, truncating to 5000")
        text = text[:5000]

    # Create file URL with encoded text parameter
    file_url = HTML_FILE.as_uri()
    full_url = f"{file_url}?text={urllib.parse.quote(text)}"

    word_count = len(text.split())
    print(f"Opening typing practice with {word_count} words...")
    print("Press Tab to restart")

    # Open in default browser
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
    else:
        # Treat all arguments as the practice text
        text = ' '.join(sys.argv[1:])

    launch_practice(text)


if __name__ == '__main__':
    main()
