#!/usr/bin/env python3
"""
Launch typing practice session with custom text.

Opens Monkeytype in your default browser with custom text via URL parameter.

Usage:
    python3 practice.py "Your practice text here"
    python3 practice.py --file path/to/text.txt
    echo "text" | python3 practice.py --file -

Note: Digraph highlighting (--hardest, --fastest, --digraphs) was removed since
Monkeytype doesn't support these features. Use the old HTML file (.bak) if needed.
"""

import sys
import webbrowser
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.monkeytype_url import generate_custom_text_url, get_url_info


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


def launch_practice(text: str, mode: str = "repeat"):
    """Launch typing practice in Monkeytype via URL."""
    url = generate_custom_text_url(text, mode)
    info = get_url_info(url)

    word_count = len(text.split())
    print(f"🐵 Opening Monkeytype with {word_count} words...")
    print(f"   URL length: {info['url_length']} characters")
    print(f"   Press Tab to restart")

    # Open in default browser
    webbrowser.open(url)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    text: str | None = None
    filepath: str | None = None
    mode = "repeat"

    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]

        if arg == "--file":
            if i + 1 >= len(sys.argv):
                print("Error: --file requires a filepath argument", file=sys.stderr)
                sys.exit(1)
            filepath = sys.argv[i + 1]
            i += 2
        elif arg == "--mode":
            if i + 1 >= len(sys.argv):
                print("Error: --mode requires a mode argument (repeat/zip/max)", file=sys.stderr)
                sys.exit(1)
            mode = sys.argv[i + 1]
            i += 2
        elif arg.startswith("--"):
            print(f"Warning: {arg} option not supported with Monkeytype (ignored)")
            i += 1
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

    launch_practice(text, mode)


if __name__ == "__main__":
    main()
