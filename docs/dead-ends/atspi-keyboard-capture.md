# AT-SPI Keyboard Capture - DEAD END

## Status: DOES NOT WORK on KDE Plasma Wayland

This approach for capturing keyboard events using the AT-SPI (Assistive Technology Service Provider Interface) framework **does not work** on KDE Plasma 6.5.2 Wayland.

## Problem

On KDE Plasma Wayland, AT-SPI `registerKeystrokeListener()` either:
1. Returns `False` (registration failed)
2. Returns `True` but captures **ZERO** keyboard events

Even with the AT-SPI D-Bus service running and correct API usage, global keyboard events are blocked by KDE Plasma's Wayland compositor security model.

## Why It Doesn't Work

KDE Plasma on Wayland has a different security model than GNOME or X11:
- The compositor filters keyboard events at the Wayland protocol level
- Global keyboard event capture is blocked for privacy/security reasons
- AT-SPI works fine for other accessibility features but NOT for keyboard sniffing
- This is a platform limitation, NOT a code bug

## Files Using This Approach

### Core Implementation
- `core/event_handler.py` - Full EventHandler class using AT-SPI

### Test Scripts
- `test_atspi.py` - Initial AT-SPI test
- `test_atspi_fixed.py` - Fixed version
- `test_atspi_final.py` - Final iteration
- `test_atspi_working.py` - Diagnosis script
- `discover_registry.py` - AT-SPI registry discovery

### Setup Scripts
- `enable_accessibility.sh` - AT-SPI service enablement

### Documentation
- `docs/references/AT_SPI_ISSUES.md` - Detailed issue documentation

## What We Tried

1. ✅ Fixed AT-SPI API usage
   - Correct Registry instantiation
   - Proper `registerKeystrokeListener()` parameters
   - All proper error handling

2. ✅ Enabled AT-SPI services
   - at-spi-dbus-bus.service running
   - at-spi-dbus-bus-launcher.service running

3. ❌ Still ZERO keyboard events captured

## References

- Existing docs: `docs/references/AT_SPI_ISSUES.md`
- [KDE Accessibility Documentation](https://docs.kde.org/stable/en/plasma-desktop/accessibility-kde/)
- [Wayland Security Model](https://wayland.freedesktop.org/docs/html/spec.html)

## Solution Used Instead

The project now uses **evdev** (/dev/input/eventX) for keyboard event capture, which works at a lower level and bypasses the compositor restrictions.

## Notes

- AT-SPI works on X11 and GNOME Wayland
- This is KDE Plasma Wayland specific
- Not recommended for further development effort
- Code kept for reference/documentation purposes
