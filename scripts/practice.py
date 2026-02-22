#!/usr/bin/env python3
"""
Launch typing practice session with custom text.

Opens the standalone typing practice page in your default browser.

Usage:
    python3 practice.py "Your practice text here"
    python3 practice.py --file path/to/text.txt
    python3 practice.py --file - [--hardest words] [--fastest words] [--digraphs dg,dg]
    echo "text" | python3 practice.py --file -
"""

import sys
import urllib.parse
import webbrowser
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
HTML_FILE = SCRIPT_DIR / "typing_practice.html"


def get_text_from_file(filepath: str) -> str:
    """Read text from file."""
    if filepath == "-":
        # Read from stdin
        return sys.stdin.read()

    path = Path(filepath)
    if not path.exists():
        print(f"Error: File not found: {filepath}", file=sys.stderr)
        sys.exit(1)
    return path.read_text()


def launch_practice(
    text: str,
    hardest_words: list[str] | None = None,
    fastest_words: list[str] | None = None,
    digraphs: list[str] | None = None,
):
    """Launch typing practice in default browser."""
    # Create file URL with encoded text parameter
    file_url = HTML_FILE.as_uri()
    params = {"text": text}
    if hardest_words:
        params["hardest"] = ",".join(hardest_words)
    if fastest_words:
        params["fastest"] = ",".join(fastest_words)
    if digraphs:
        params["digraphs"] = ",".join(digraphs)
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
    fastest_words: list[str] | None = None
    digraphs: list[str] | None = None
    text: str | None = None
    filepath: str | None = None

    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]

        if arg == "--file":
            if i + 1 >= len(sys.argv):
                print("Error: --file requires a filepath argument", file=sys.stderr)
                sys.exit(1)
            filepath = sys.argv[i + 1]
            i += 2
        elif arg == "--hardest":
            if i + 1 >= len(sys.argv):
                print("Error: --hardest requires comma-separated words", file=sys.stderr)
                sys.exit(1)
            hardest_words = sys.argv[i + 1].split(",")
            i += 2
        elif arg == "--fastest":
            if i + 1 >= len(sys.argv):
                print("Error: --fastest requires comma-separated words", file=sys.stderr)
                sys.exit(1)
            fastest_words = sys.argv[i + 1].split(",")
            i += 2
        elif arg == "--digraphs":
            if i + 1 >= len(sys.argv):
                print("Error: --digraphs requires comma-separated digraphs", file=sys.stderr)
                sys.exit(1)
            digraphs = sys.argv[i + 1].split(",")
            i += 2
        else:
            # Treat remaining arguments as the practice text
            text = " ".join(sys.argv[i:])
            break

    # Determine text source
    if filepath is not None:
        text = get_text_from_file(filepath)
    elif text is None:
        print("Error: No text provided", file=sys.stderr)
        sys.exit(1)

    launch_practice(text, hardest_words, fastest_words, digraphs)


if __name__ == "__main__":
    main()
