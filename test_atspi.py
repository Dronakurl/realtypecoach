#!/usr/bin/env python3
"""Test script to verify AT-SPI keyboard events are being received."""

import sys
import time

import pyatspi
import pyatspi.registry as registry

print("=" * 50)
print("AT-SPI Keyboard Event Test")
print("=" * 50)

keyboard_event_count = 0


def on_keyboard_event(event):
    """Handle keyboard event."""
    global keyboard_event_count
    keyboard_event_count += 1

    try:
        key_code = event.hw_code
        event_string = event.event_string
    except AttributeError:
        key_code = event.event_code if hasattr(event, 'event_code') else 'unknown'
        event_string = 'unknown'
    
    if event.type == pyatspi.EventType.KEY_PRESSED:
        print(f"✓ KEY PRESS: code={key_code}, string='{event_string}'")
    else:
        print(f"  KEY RELEASE: code={key_code}, string='{event_string}'")

    if keyboard_event_count >= 10:
        print("\n✓ Received 10 keyboard events - AT-SPI is working!")
        print("Press Ctrl+C to exit")
        return True
    return False


try:
    print("Initializing AT-SPI...")
    
    print("Registering keyboard event listener...")
    # Try module-level function first
    try:
        pyatspi.registerKeystrokeListener(on_keyboard_event)
        print("✓ Used module-level registerKeystrokeListener")
    except AttributeError:
        # Try registry object method
        try:
            registry = pyatspi.Registry()
            registry.registerKeystrokeListener(on_keyboard_event)
            print("✓ Used registry.registerKeystrokeListener")
        except AttributeError:
            # Try generic event listener
            registry = pyatspi.Registry()
            registry.registerEventListener(on_keyboard_event, 'keystroke')
            print("✓ Used generic registerEventListener with 'keystroke'")
    
    print("✓ AT-SPI initialized and listener registered")
    print("="*50)
    print("Start typing to test keyboard event capture...")
    print("This script will exit after 10 key presses.")
    print("="*50)
    print

    while True:
        time.sleep(1)

except KeyboardInterrupt:
    print("\n\nTest interrupted by user.")
    try:
        pyatspi.deregisterKeystrokeListener(on_keyboard_event)
    except:
        pass
    sys.exit(0)

except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
