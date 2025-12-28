#!/usr/bin/env python3
"""Final AT-SPI test using correct API."""

import sys
import time

print("=" * 60)
print("AT-SPI Keyboard Event Test - Final Version")
print("=" * 60)

try:
    import pyatspi
    print("✓ pyatspi imported")
    
    import pyatspi.registry as registry
    print("✓ pyatspi.registry imported")
    
    keyboard_event_count = 0
    
    def on_keyboard_event(event):
        """Handle keyboard event using AT-SPI 2.46+ API."""
        global keyboard_event_count
        keyboard_event_count += 1
        
        print(f"✓ EVENT #{keyboard_event_count}: type={event.type}, detail={event.detail}")
        print(f"  hw_code={event.hw_code if hasattr(event, 'hw_code') else 'N/A'}")
        print(f"  is_text={event.is_text}")
        print(f"  keyval={event.keyval if hasattr(event, 'keyval') else 'N/A'}")
        
        if keyboard_event_count >= 10:
            print("\n✓✓ SUCCESS! Received 10 events - AT-SPI is WORKING!")
            print("Press Ctrl+C to exit")
            return True
        return False
    
    print("\n" + "-" * 60)
    print("Registering keystroke listener...")
    print("-" * 60 + "\n")
    
    # Try correct API
    try:
        result = registry.registerKeystrokeListener(
            on_keyboard_event,
            synchronous=False,  # Allow async event delivery
            preemptive=True,  # Preempt other listeners
            global_=False
        )
        if result:
            print("✓ Keystroke listener registered successfully!")
        else:
            print("✗ Listener registration returned False")
    except AttributeError as e:
        print(f"✗ registerKeystrokeListener not available: {e}")
        print("\n" + "-" * 60)
        print("Trying alternative methods...")
        print("-" * 60 + "\n")
        
        try:
            registry = pyatspi.Registry.get_instance()
            print("✓ Got registry singleton")
            print("\nAttempting to register listener...")
            print("Type some keys to test...")
            print("-" * 60 + "\n")
        except Exception as e2:
            print(f"✗ Could not get registry instance: {e2}")
            sys.exit(1)
    
    print("=" * 60)
    print("Starting 10-second test window...")
    print("Type some keys now!")
    print("=" * 60)
    print()
    
    import signal
    def handler(signum, frame):
        print("\n\nTest stopped by user.")
        try:
            registry.deregisterKeystrokeListener(on_keyboard_event)
        except:
            pass
        sys.exit(0)
    
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)
    
    start = time.time()
    while time.time() - start < 10:
        time.sleep(0.1)
    
    if keyboard_event_count == 0:
        print("\n" + "!" * 60)
        print("✗ FAILURE - NO keyboard events captured!")
        print("!" * 60)
        print("\nThis means AT-SPI is NOT receiving events from KDE")
        print("\nPOSSIBLE CAUSES:")
        print("1. KDE Accessibility is disabled in System Settings")
        print("2. AT-SPI D-Bus services not running properly")
        print("3. KDE security blocking accessibility")
        print("\nSOLUTIONS TO TRY:")
        print("1. System Settings → Workspace Behavior → Accessibility")
        print("2. Toggle ALL accessibility options ON")
        print("3. Log out and log back in")
        print("4. Reboot if needed")
    else:
        print("\n✓ Test PASSED - AT-SPI is working!")
    
except ImportError as e:
    print(f"\n✗ pyatspi not available: {e}")
    print("\nInstall with: sudo apt install python3-pyatspi at-spi2-core")
    sys.exit(1)
except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
