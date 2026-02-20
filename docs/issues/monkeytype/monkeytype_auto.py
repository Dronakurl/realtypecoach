#!/usr/bin/env python3
"""
Automatically inject custom text into Monkeytype using browser automation.

This script uses Playwright to open Monkeytype and inject text via JavaScript.

Requirements:
    pip install playwright
    playwright install chromium

Usage:
    python3 monkeytype_auto.py "Your text here"
    python3 monkeytype_auto.py --file text.txt
    python3 monkeytype_auto.py --headless=false "text"
"""

import sys
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Error: playwright not installed.")
    print("Install with: pip install playwright")
    print("Then run: playwright install chromium")
    sys.exit(1)


def inject_text_monkeytype(
    text: str, mode: str = "repeat", headless: bool = False, url: str = "https://monkeytype.com"
):
    """
    Open Monkeytype and inject custom text using browser automation.
    """

    words = text.split()

    injection_script = f"""
    (function() {{
        const customTextSettings = {{
            text: {words!s},
            mode: "{mode}",
            limit: {{
                value: {len(words)},
                mode: "word"
            }},
            pipeDelimiter: false
        }};

        localStorage.setItem('customTextSettings', JSON.stringify(customTextSettings));

        // Set mode to custom
        const configEvent = new CustomEvent('configEvent', {{
            detail: {{ mode: 'custom' }}
        }});
        window.dispatchEvent(configEvent);

        return "Injection successful!";
    }})();
    """

    with sync_playwright() as p:
        print(f"🐵 Opening browser and navigating to {url}...")

        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()

        # Navigate to Monkeytype
        page.goto(url)

        print("📝 Injecting custom text...")

        # Execute injection script
        result = page.evaluate(injection_script)

        print(f"✅ {result}")

        # Reload to apply changes
        print("🔄 Reloading page to apply custom text...")
        page.reload(wait_until="networkidle")

        print(f"\n{'=' * 60}")
        print("✨ SUCCESS! Monkeytype is now open with your custom text:")
        print(f"   - Words: {len(words)}")
        print(f"   - Characters: {len(text)}")
        print(f"   - Mode: {mode}")
        print(f"{'=' * 60}\n")

        # Keep browser open
        print("Browser is open. Press Ctrl+C to close...")
        try:
            page.wait_for_timeout(300000)  # Wait 5 minutes or until user closes
        except KeyboardInterrupt:
            print("\nClosing browser...")
        finally:
            browser.close()


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
        print("\nModes: repeat, zip, maximize")
        sys.exit(1)

    mode = "repeat"
    headless = False
    url = "https://monkeytype.com"
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
        elif arg == "--headless":
            headless = arg == "true" or sys.argv[i + 1] == "true" if i + 1 < len(sys.argv) else True
            i += 2 if i + 1 < len(sys.argv) and not sys.argv[i + 1].startswith("--") else 1
        elif arg == "--url":
            if i + 1 >= len(sys.argv):
                print("Error: --url requires URL")
                sys.exit(1)
            url = sys.argv[i + 1]
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

    try:
        inject_text_monkeytype(text, mode, headless, url)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nTroubleshooting:")
        print("1. Make sure playwright is installed: pip install playwright")
        print("2. Install browser: playwright install chromium")
        print("3. Check your internet connection")
        sys.exit(1)


if __name__ == "__main__":
    main()
