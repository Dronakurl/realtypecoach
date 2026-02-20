#!/usr/bin/env python3
"""
Inject custom text into Monkeytype via browser console.

This generates JavaScript code that you paste into the browser console
on monkeytype.com.

Usage:
    python3 monkeytype_console.py "Your text here"
    python3 monkeytype_console.py --file text.txt
"""

import json
import sys
from pathlib import Path


def generate_injection_code(text: str, mode: str = "repeat"):
    """Generate JavaScript injection code."""

    words = text.split()

    code = f"""
// RealTypeCoach Monkeytype Text Injector
(function() {{
    const text = {json.dumps(words)};
    const customTextSettings = {{
        text: text,
        mode: "{mode}",
        limit: {{
            value: text.length,
            mode: "word"
        }},
        pipeDelimiter: false
    }};

    localStorage.setItem('customTextSettings', JSON.stringify(customTextSettings));
    console.log('✅ Text injected! Reloading...');
    location.reload();
}})();
"""

    return code.strip()


def show_instructions(text: str, mode: str):
    """Display usage instructions."""

    code = generate_injection_code(text, mode)

    instructions = f"""
╔══════════════════════════════════════════════════════════════════════╗
║  MONKEYTYPE CUSTOM TEXT INJECTION                                    ║
╚══════════════════════════════════════════════════════════════════════╝

Your custom text ({len(text.split())} words, {len(text)} chars)

Steps:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Open Vivaldi
2. Go to: https://monkeytype.com
3. Press F12 (Developer Tools)
4. Click "Console" tab
5. Paste the code below (it's already copied for you!)
6. Press Enter

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

    print(instructions)

    # Try to copy to clipboard
    try:
        import pyperclip

        pyperclip.copy(code)
        print("✅ Code copied to clipboard!")
        print()
    except ImportError:
        print("⚠️  Install pyperclip to auto-copy: pip install pyperclip")
        print()

    # Show the code
    print("Paste this code:")
    print("─" * 70)
    print(code)
    print("─" * 70)


def get_text_from_file(filepath: str) -> str:
    """Read text from file."""
    path = Path(filepath)
    if not path.exists():
        print(f"Error: File not found: {filepath}")
        sys.exit(1)
    return path.read_text()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nOptions:")
        print("  --file FILE    Read text from file")
        print("  --mode MODE    Mode: repeat, zip, maximize")
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

    show_instructions(text, mode)


if __name__ == "__main__":
    main()
