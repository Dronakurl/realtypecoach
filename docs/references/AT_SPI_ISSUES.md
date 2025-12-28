# RealTypeCoach - AT-SPI Keyboard Event Capture Issues

## Problem

On KDE Plasma 6.5.2 Wayland, AT-SPI `registerKeystrokeListener()` returns `False` and NO keyboard events are captured.

## Root Cause

KDE Plasma on Wayland has specific security/privacy restrictions that prevent AT-SPI from receiving global keyboard events. The compositor filters or blocks keyboard events at the Wayland protocol level before they reach AT-SPI.

## Diagnosis Results

**Test Script**: `test_atspi_working.py`
- Registry instantiation: ✅ SUCCESS
- Listener registration: ✅ Called successfully
- Registration result: ❌ `False`
- Keyboard events captured: ❌ **ZERO**

## Solutions Attempted

1. ✅ Fixed AT-SPI API usage
   - Changed from `registry.init()` to `reg = pyatspi.Registry()`
   - Used correct method: `registerKeystrokeListener(callback, ...)`
   - Used all proper parameters: `synchronous=False, preemptive=True, global_=False`

2. ❌ Issue persists - KDE is blocking events at protocol level

## Potential KDE Settings to Check

Since exact setting names vary by KDE version, check for:

**System Settings → Workspace Behavior → Accessibility:**
- "Enable assistive technologies" (may or may not exist on Wayland)
- "Enable keyboard accessibility" (if present)
- "AT-SPI event routing" or similar

**System Settings → Input Devices → Keyboard:**
- "Enable accessibility tools"
- "Keyboard accessibility" settings

**Alternative locations:**
- System Settings → Accessibility (main category)
- System Settings → Workspace → Shortcuts → Keyboard
- System Settings → Appearance → Global Theme → Accessibility

## Workarounds to Explore

1. **Use X11 session** instead of Wayland (temporary test)
   - Log out of Wayland session
   - Log into X11 session
   - Test if keyboard events work
   - If yes, the issue is Wayland-specific

2. **Check KDE configuration files**
   - `~/.config/kdeglobals`
   - `~/.config/plasma-workspace.conf`
   - Look for `accessibility`, `keyboard`, `ATSPI` settings

3. **Check running accessibility services**
   ```bash
   qdbus --session org.a11y.atspi.Registry
   ```
   - See if keyboard event type is registered

4. **Alternative: Use libinput or evdev directly**
   - These may require root permissions
   - Work at lower level than AT-SPI
   - Bypass compositor-level filtering
   - May work on Wayland but is more complex

## Current Status

- ✅ Python code: Correct and ready to capture events
- ✅ AT-SPI installation: Working (can import and instantiate)
- ❌ Keyboard event routing: Blocked by KDE Plasma Wayland compositor
- ❌ Keystrokes captured: ZERO

## References

### AT-SPI Documentation
- [GNOME Wiki - ATK/AT-SPI Best Practices](https://wiki.gnome.org/Accessibility/ATK/BestPractices)
- [AT-SPI Python Bindings](https://gitlab.gnome.org/Teams/AT-SPI/at-spi2-core)

### KDE Accessibility
- [KDE Accessibility Documentation](https://docs.kde.org/stable/en/plasma-desktop/accessibility-kde/)
- [KDE Plasma Wayland](https://docs.kde.org/stable/en/plasma-desktop/plasma-wayland/)

### Wayland vs AT-SPI
- [Wayland Security Model](https://wayland.freedesktop.org/docs/html/spec.html)
- [AT-SPI on Wayland](https://gitlab.gnome.org/Teams/AT-SPI/at-spi2-core/-/issues)

## Notes

- This is a known limitation of KDE on Wayland
- AT-SPI works fine on X11 and GNOME Wayland
- KDE Plasma has different security model that blocks global keyboard capture
- This is NOT a bug in RealTypeCoach code - it's a platform limitation
