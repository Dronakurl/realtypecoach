#!/usr/bin/env python3
"""Simple AT-SPI test to verify keyboard event capture."""

import sys
import time

try:
    import pyatspi
    print("✓ pyatspi imported")
except ImportError as e:
    print(f"✗ pyatspi not available: {e}")
    sys.exit(1)

try:
    import pyatspi.registry as registry
    print("✓ pyatspi.registry imported")
except ImportError as e:
    print(f"✗ pyatspi.registry not available: {e}")
    sys.exit(1)

print("=" * 60)
print("AT-SPI Simple Registration Test")
print("=" * 60)
print()

keyboard_event_count = 0

def on_keyboard_event(event):
    """Handle keyboard event."""
    global keyboard_event_count
    keyboard_event_count += 1
    
    try:
        if hasattr(event, 'type'):
            event_type_str = "PRESSED" if event.type == 1 else "RELEASED"
        else:
            event_type_str = "unknown"
    except:
        event_type_str = "unknown"
    
    try:
        if hasattr(event, 'hw_code'):
            code = event.hw_code
        elif hasattr(event, 'event_code'):
            code = event.event_code
        else:
            code = "N/A"
    except:
        code = "N/A"
    
    print(f"✓ EVENT #{keyboard_event_count}: type={event_type_str}, code={code}")

    if keyboard_event_count >= 5:
        print("\n✓✓✓ SUCCESS! Received 5 keyboard events!")
        print("AT-SPI is WORKING!")
        return True
    return False

try:
    print("Creating Registry instance...")
    reg = pyatspi.Registry()
    print(f"✓ Registry created: {reg}")
    
    print("\nRegistering keystroke listener...")
    result = reg.registerKeystrokeListener(
        on_keyboard_event,
        synchronous=False,
        preemptive=True,
        global_=False
    )
    print(f"✓ Listener registered: {result}")
    
    if not result:
        print("⚠️  Registration returned False - may indicate issue")
    
    print("=" * 60)
    print("Starting 10-second test window...")
    print("TYPE SOME KEYS NOW!")
    print("=" * 60)
    print()
    
    import signal
    
    def handler(signum, frame):
        print("\n\nTest stopped by user")
        reg.deregisterKeystrokeListener(on_keyboard_event)
        sys.exit(0)
    
    signal.signal(signal.SIGINT, handler)
    
    start = time.time()
    while time.time() - start < 10:
        time.sleep(0.1)
    
    if keyboard_event_count == 0:
        print("\n" + "!" * 60)
        print("✗ FAILURE - NO keyboard events captured")
        print("!" * 60)
        print("\nPOSSIBLE REASONS:")
        print("1. KDE Accessibility is not routing keyboard events to AT-SPI")
        print("2. KDE Plasma 6.5.2 has specific Wayland keyboard event blocking")
        print("3. AT-SPI version incompatibility")
        print("\nCHECK KDE SETTINGS:")
        print("System Settings → Workspace Behavior → Accessibility")
        print("Look for ANY keyboard-related accessibility options")
        print("=" * 60)
    else:
        print(f"\n✓ Test completed with {keyboard_event_count} events captured")
    
except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
