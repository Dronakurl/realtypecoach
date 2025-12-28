#!/usr/bin/env python3
"""Test script to verify AT-SPI keyboard events are being received."""

import sys
import pyatspi
import pyatspi.registry as registry
import time

print("="*50)
print("AT-SPI Keyboard Event Test")
print("="*50)
print

keyboard_event_count = 0

def on_keyboard_event(event):
    """Handle keyboard event."""
    global keyboard_event_count
    keyboard_event_count += 1

    if event.event_string == 'press':
        print(f"✓ KEY PRESS: code={event.event_code}, string='{event.event_string}'")
    else:
        print(f"  KEY RELEASE: code={event.event_code}, string='{event.event_string}'")

    if keyboard_event_count >= 10:
        print("\n✓ Received 10 keyboard events - AT-SPI is working!")
        print("Press Ctrl+C to exit")
        return True
    return False

try:
    print("Initializing AT-SPI...")
    registry.init()

    print("Registering keyboard event listener...")
    registry.registerEventListener(on_keyboard_event, 'keyboard')

    print("✓ AT-SPI initialized and listener registered")
    print
    print("="*50)
    print("Start typing to test keyboard event capture...")
    print("This script will exit after 10 key presses.")
    print("="*50)
    print

    while True:
        time.sleep(1)

except KeyboardInterrupt:
    print("\n\nTest interrupted by user.")
    registry.deregisterEventListener(on_keyboard_event)
    registry.stop()
    sys.exit(0)

except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
