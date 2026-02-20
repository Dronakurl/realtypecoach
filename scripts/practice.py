#!/usr/bin/env python3
"""
Launch typing practice session with custom text.

Opens the standalone typing practice page in your default browser.

Usage:
    python3 practice.py "Your practice text here"
    python3 practice.py --file path/to/text.txt
"""

import sys
import urllib.parse
import webbrowser
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


def launch_practice(text: str, hardest_words: list[str] | None = None):
    """Launch typing practice in default browser."""
    # Create file URL with encoded text parameter
    file_url = HTML_FILE.as_uri()
    params = {"text": text}
    if hardest_words:
        params["hardest"] = ",".join(hardest_words)
    query_string = urllib.parse.urlencode(params, safe="")
    full_url = f"{file_url}?{query_string}"

    word_count = len(text.split())
    print(f"Opening typing practice with {word_count} words...")
    print("Press Tab to restart")

    # Open in default browser
    webbrowser.open(full_url)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    hardest_words: list[str] | None = None

    if sys.argv[1] == "--file":
        if len(sys.argv) < 3:
            print("Error: --file requires a filepath argument")
            sys.exit(1)
        text = get_text_from_file(sys.argv[2])
    elif sys.argv[1] == "--hardest":
        if len(sys.argv) < 4:
            print("Error: --hardest requires a filepath and comma-separated words")
            sys.exit(1)
        text = get_text_from_file(sys.argv[2])
        hardest_words = sys.argv[3].split(",")
    else:
        # Treat all arguments as the practice text
        text = " ".join(sys.argv[1:])

    launch_practice(text, hardest_words)


if __name__ == "__main__":
    main()
