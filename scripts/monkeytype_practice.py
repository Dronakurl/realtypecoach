#!/usr/bin/env python3
"""
Launch Monkeytype with custom text injection.

This script injects custom text into Monkeytype's localStorage and opens it.

Usage:
    python3 monkeytype_practice.py "Your practice text here"
    python3 monkeytype_practice.py --file path/to/text.txt
    python3 monkeytype_practice.py --url http://localhost:3000 "text"
    python3 monkeytype_practice.py --mode zip "text for zip mode"
"""
import sys
import webbrowser
import urllib.parse
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
INJECTOR_HTML = SCRIPT_DIR / "monkeytype_inject.html"

# Default Monkeytype URLs
DEFAULT_LOCAL_URL = "http://localhost:3000"
DEFAULT_ONLINE_URL = "https://monkeytype.com"


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


def launch_monkeytype(text: str, monkeytype_url: str = DEFAULT_LOCAL_URL, mode: str = "repeat", long: bool = False):
    """
    Launch Monkeytype with injected custom text.

    Args:
        text: The practice text to inject
        monkeytype_url: URL of Monkeytype instance (local or online)
        mode: Monkeytype custom mode (repeat, zip, maximize)
        long: Whether to save as long text
    """
    # Truncate text if too long (URL limits)
    if len(text) > 10000:
        print(f"Warning: Text is {len(text)} chars, truncating to 10000")
        text = text[:10000]

    # Create file URL with encoded parameters
    file_url = INJECTOR_HTML.as_uri()
    params = {
        "text": text,
        "url": monkeytype_url,
        "mode": mode,
        "long": "true" if long else "false"
    }

    # Build query string
    query_string = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    full_url = f"{file_url}?{query_string}"

    word_count = len(text.split())
    print(f"🐵 Opening Monkeytype with {word_count} words...")
    print(f"   Mode: {mode}")
    print(f"   URL: {monkeytype_url}")
    print(f"   Text length: {len(text)} characters")

    webbrowser.open(full_url)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nModes:")
        print("  repeat  - Repeat the text (default)")
        print("  zip     - Zip mode (remove typed words)")
        print("  maximize - Maximize mode (infinite)")
        sys.exit(1)

    # Parse arguments
    monkeytype_url = DEFAULT_LOCAL_URL
    mode = "repeat"
    long = False
    text_args_start = 1

    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--file":
            if i + 1 >= len(sys.argv):
                print("Error: --file requires a filepath argument")
                sys.exit(1)
            text = get_text_from_file(sys.argv[i + 1])
            text_args_start = i + 2
            break
        elif arg == "--clipboard":
            text = get_text_from_clipboard()
            if not text:
                print("Error: Clipboard is empty")
                sys.exit(1)
            text_args_start = i + 1
            break
        elif arg == "--url":
            if i + 1 >= len(sys.argv):
                print("Error: --url requires a URL argument")
                sys.exit(1)
            monkeytype_url = sys.argv[i + 1]
            text_args_start = i + 2
        elif arg == "--mode":
            if i + 1 >= len(sys.argv):
                print("Error: --mode requires a mode argument (repeat/zip/maximize)")
                sys.exit(1)
            mode = sys.argv[i + 1]
            text_args_start = i + 2
        elif arg == "--long":
            long = True
            text_args_start = i
        elif arg.startswith("--"):
            print(f"Error: Unknown option {arg}")
            sys.exit(1)
        else:
            # First non-option argument is the start of text
            text = ' '.join(sys.argv[i:])
            text_args_start = i
            break

    # If no text was set via --file or --clipboard, get from remaining args
    if "text" not in locals():
        if text_args_start >= len(sys.argv):
            print("Error: No text provided")
            sys.exit(1)
        text = ' '.join(sys.argv[text_args_start:])

    launch_monkeytype(text, monkeytype_url, mode, long)


if __name__ == "__main__":
    main()
