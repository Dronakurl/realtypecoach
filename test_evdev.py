#!/usr/bin/env python3
"""Test script to verify evdev keyboard events are being received."""

import sys
import time

try:
    from evdev import InputDevice, list_devices, ecodes
except ImportError:
    print("Error: evdev module not installed. Install with: sudo apt install python3-evdev")
    sys.exit(1)

print("=" * 50)
print("evdev Keyboard Event Test")
print("=" * 50)

# Find keyboard devices
print("\nScanning for keyboard devices...")
keyboards = []
for path in list_devices():
    try:
        device = InputDevice(path)
        if ecodes.EV_KEY in device.capabilities():
            caps = device.capabilities()[ecodes.EV_KEY]
            has_letter_keys = any(
                ecodes.KEY_A <= code <= ecodes.KEY_Z or
                code in [ecodes.KEY_SPACE, ecodes.KEY_ENTER, ecodes.KEY_ESC]
                for code in caps
            )
            if has_letter_keys:
                keyboards.append(device)
                print(f"  ✓ Found keyboard: {device.name} at {path}")
    except PermissionError:
        print(f"  ✗ Permission denied: {path}")
        print("    You need to be in the 'input' group:")
        print("      sudo usermod -aG input $USER")
        print("    Then log out and log back in.")
        sys.exit(1)
    except OSError as e:
        print(f"  ✗ Error accessing {path}: {e}")

if not keyboards:
    print("\n✗ No keyboard devices found!")
    sys.exit(1)

print(f"\n✓ Found {len(keyboards)} keyboard device(s)")
print("=" * 50)
print("Start typing to test keyboard event capture...")
print("Press Ctrl+C to exit")
print("=" * 50)

event_count = 0
try:
    from select import select

    while True:
        r, _, _ = select(keyboards, [], [], 0.1)

        for device in r:
            try:
                for event in device.read():
                    if event.type == ecodes.EV_KEY:
                        event_count += 1

                        if event.value == 1:  # Press
                            print(f"✓ KEY PRESS: code={event.code}")
                        elif event.value == 0:  # Release
                            print(f"  KEY RELEASE: code={event.code}")

                        if event_count >= 10:
                            print("\n✓ Received 10 keyboard events - evdev is working!")
                            print("Press Ctrl+C to exit")

            except OSError:
                continue

except KeyboardInterrupt:
    print(f"\n\nTotal events captured: {event_count}")
    print("✓ Test completed successfully")
    sys.exit(0)

except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
