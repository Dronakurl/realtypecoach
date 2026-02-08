#!/usr/bin/env python3
"""
Launch Monkeytype in Vivaldi with injected custom text.

This script sets up the text and opens Vivaldi. A userscript in Vivaldi
detects the injected text and applies it to Monkeytype.

Requirements:
    1. Install Tampermonkey extension in Vivaldi
    2. Add the userscript from scripts/monkeytype_injector.user.js
    3. Run this script to inject text

Usage:
    python3 vivaldi_launch.py "Your text here"
    python3 vivaldi_launch.py --file text.txt
"""
import sys
import webbrowser
import urllib.parse
from pathlib import Path


def setup_userscript():
    """Show instructions for setting up the userscript."""

    userscript_path = Path(__file__).parent / "monkeytype_injector.user.js"

    instructions = """
╔══════════════════════════════════════════════════════════════════════╗
║  MONKEYTYPE CUSTOM TEXT INJECTION - FIRST TIME SETUP                 ║
╚══════════════════════════════════════════════════════════════════════╝

One-time setup required:

1. Install Tampermonkey in Vivaldi:
   - Go to Chrome Web Store
   - Search "Tampermonkey"
   - Click "Add to Vivaldi"

2. Add the userscript:
   - Click the Tampermonkey icon
   - Dashboard → Create a new script
   - Copy the contents of this file:
   """
    print(instructions)
    print(f"   {userscript_path}")
    print("""
   - Paste it into the editor
   - File → Save

3. Enable the script for monkeytype.com

That's it! Now you can inject custom text.
"""
    )


def inject_and_launch(text: str, mode: str = "repeat"):
    """
    Inject text into localStorage and open Vivaldi.
    """

    # Store injection data in a special localStorage key via a data URL
    injection_data = {
        "text": text,
        "mode": mode
    }

    # Create a simple HTML page that sets localStorage and redirects
    html_injector = f"""
<!DOCTYPE html>
<html>
<head><title>Injecting...</title></head>
<body>
<script>
// Set the injection data
localStorage.setItem('rtc_injectedText', JSON.stringify({json.dumps(injection_data)});
// Redirect to Monkeytype
window.location.href = 'https://monkeytype.com';
</script>
</body>
</html>
"""

    # Write to a temp file
    import tempfile
    import json

    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write(html_injector)
        temp_path = f.name

    try:
        temp_file = Path(temp_path)
        file_url = temp_file.as_uri()

        word_count = len(text.split())

        print(f"🐵 Launching Vivaldi with custom text...")
        print(f"   Words: {word_count}")
        print(f"   Characters: {len(text)}")
        print(f"   Mode: {mode}")
        print()

        # Open in Vivaldi
        webbrowser.get('vivaldi').open(file_url)

        print("✅ Vivaldi should open with Monkeytype!")
        print("   The userscript will automatically apply your custom text.")

    finally:
        # Clean up temp file after a delay
        import time
        time.sleep(5)
        try:
            Path(temp_path).unlink()
        except:
            pass


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
        print("  --setup        Show setup instructions")
        print("\nModes: repeat, zip, maximize")
        sys.exit(1)

    mode = "repeat"
    text = None

    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]

        if arg == "--setup":
            setup_userscript()
            sys.exit(0)
        elif arg == "--file":
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
            text = ' '.join(sys.argv[i:])
            break

    if not text:
        print("Error: No text provided")
        sys.exit(1)

    # Check if userscript exists
    userscript_path = Path(__file__).parent / "monkeytype_injector.user.js"
    if not userscript_path.exists():
        print("⚠️  Warning: userscript not found!")
        print("   Run with --setup for instructions")
        print()

    inject_and_launch(text, mode)


if __name__ == "__main__":
    main()
