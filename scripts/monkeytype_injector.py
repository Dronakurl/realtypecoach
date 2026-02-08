#!/usr/bin/env python3
"""
Inject custom text into Monkeytype using browser automation.

This script opens Monkeytype and injects custom text via JavaScript.

Usage:
    python3 monkeytype_injector.py "Your text here"
    python3 monkeytype_injector.py --file text.txt
"""
import sys
import webbrowser
import urllib.parse
from pathlib import Path

def create_injection_script(text: str, mode: str = "repeat") -> str:
    """Create JavaScript to inject text into Monkeytype localStorage."""

    # Escape text for JavaScript
    words = text.split()
    words_json = str(words).replace("'", '"')

    script = f"""
    (function() {{
        // Set custom text in localStorage
        const customTextSettings = {{
            text: {words_json},
            mode: "{mode}",
            limit: {{
                value: {len(words)},
                mode: "word"
            }},
            pipeDelimiter: false
        }};

        localStorage.setItem('customTextSettings', JSON.stringify(customTextSettings));

        // Reload page to apply changes
        location.reload();
    }})();
    """

    # Compress to single line for URL
    return script.replace('\n', ' ').replace('  ', ' ').strip()


def create_bookmarklet(text: str, mode: str = "repeat") -> str:
    """Create a bookmarklet URL for Monkeytype injection."""

    script = create_injection_script(text, mode)
    encoded = urllib.parse.quote(script)

    return f"javascript:{encoded}"


def inject_via_clipboard(text: str):
    """Create JavaScript that user can paste in browser console."""

    script = create_injection_script(text)
    instructions = """
╔════════════════════════════════════════════════════════════════╗
║  MONKEYTYPE CUSTOM TEXT INJECTION                               ║
╚════════════════════════════════════════════════════════════════╝

1. Open https://monkeytype.com in your browser
2. Press F12 to open Developer Tools
3. Go to the "Console" tab
4. Paste the code below and press Enter

═══════════════════════════════════════════════════════════════════
"""

    print(instructions)
    print(script)
    print("\n" + "="*70)
    print("After pasting, the page will reload with your custom text!")
    print("="*70)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nModes: repeat, zip, maximize")
        sys.exit(1)

    # Parse arguments
    text = None
    mode = "repeat"

    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]

        if arg == "--file":
            if i + 1 >= len(sys.argv):
                print("Error: --file requires filepath")
                sys.exit(1)
            text = Path(sys.argv[i + 1]).read_text()
            i += 2
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
            text = ' '.join(sys.argv[i:])
            break

    if not text:
        print("Error: No text provided")
        sys.exit(1)

    # Show instructions for manual injection
    inject_via_clipboard(text)


if __name__ == "__main__":
    main()
