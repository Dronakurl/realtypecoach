#!/usr/bin/env python3
"""Test script to verify AT-SPI keyboard events are being received."""

import sys
import time

print("=" * 50)
print("AT-SPI Keyboard Event Test (Corrected)")
print("=" * 50)

try:
    import pyatspi
    print("✓ pyatspi imported successfully")
    
    import pyatspi.registry as registry
    print("✓ pyatspi.registry imported")
    
    # Check what's available
    print(f"\nRegistry class: {registry.Registry.__name__}")
    
    keyboard_event_count = 0
    
    def on_keyboard_event(event):
        """Handle keyboard event."""
        global keyboard_event_count
        keyboard_event_count += 1
        
        # Try to get event details safely
        try:
            if hasattr(event, 'type'):
                print(f"✓ KEY EVENT {keyboard_event_count}: type={event.type}")
            elif hasattr(event, 'event_string'):
                print(f"✓ KEY EVENT {keyboard_event_count}: string='{event.event_string}'")
            else:
                print(f"✓ KEY EVENT {keyboard_event_count}: {type(event)}")
        except Exception as e:
            print(f"✓ KEY EVENT {keyboard_event_count}: {event}")
        
        if keyboard_event_count >= 10:
            print("\n✓✓✓ SUCCESS! Received 10 keyboard events - AT-SPI is working!")
            print("Press Ctrl+C to exit")
            return True
        return False
    
    print("\nAttempting to register keystroke listener...")
    try:
        result = registry.registerEventListener(on_keyboard_event, 'keystroke')
        if result:
            print("✓ Keystroke listener registered successfully!")
        else:
            print("✗ Keystroke listener registration returned False")
    except Exception as e:
        print(f"✗ registerEventListener failed: {e}")
        print(f"  Trying generic event listener...")
        try:
            registry.registerEventListener(on_keyboard_event)
            print("✓ Generic event listener registered")
        except Exception as e2:
            print(f"✗ Generic listener also failed: {e2}")
            sys.exit(1)
    
    print("\n" + "=" * 50)
    print("Starting 10-second test window...")
    print("Type some keys now!")
    print("=" * 50)
    print()
    
    import signal
    
    def handler(signum, frame):
        print("\n\nTest stopped by user")
        try:
            registry.deregisterKeystrokeListener(on_keyboard_event)
        except:
            try:
                registry.deregisterEventListener(on_keyboard_event)
            except:
                pass
        sys.exit(0)
    
    signal.signal(signal.SIGINT, handler)
    
    start = time.time()
    while time.time() - start < 10:
        time.sleep(0.1)
    
    if keyboard_event_count == 0:
        print("\n" + "=" * 50)
        print("✗ NO keyboard events captured!")
        print("AT-SPI is NOT receiving events from KDE")
        print("=" * 50)
        print("\nThis usually means:")
        print("1. KDE Accessibility is disabled in System Settings")
        print("2. AT-SPI services not properly connected to KDE")
        print("3. AT-SPI 2.52 version compatibility issues")
        print("\nSOLUTIONS TO TRY:")
        print("1. Open System Settings → Workspace Behavior → Accessibility")
        print("2. Look for ANY toggle related to accessibility")
        print("3. Enable all accessibility options")
        print("4. Apply changes")
        print("5. Run this test again: python3 test_atspi_fixed.py")
        print("6. If still not working, try: qdbus org.a11y.atspi.Registry")
        print("7. Reboot if needed")
        print()
        print("ALTERNATIVE: Check if KDE Accessibility is blocking non-screen readers")
        print("Look for option: 'Only allow screen readers to use AT-SPI'")
        print("This option DISABLES keyboard event capture!")
    else:
        print("\n✓ Test completed successfully!")

except ImportError as e:
    print(f"\n✗ pyatspi not available: {e}")
    print("\nInstall with:")
    print("  sudo apt install python3-pyatspi at-spi2-core")
    sys.exit(1)
except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
