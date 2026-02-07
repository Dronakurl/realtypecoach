# AT-SPI Keyboard Capture - DEAD END

**Status:** DOES NOT WORK on KDE Plasma Wayland. Abandoned in favor of evdev approach.

## Problem

On KDE Plasma Wayland, AT-SPI `registerKeystrokeListener()` either returns `False` (registration failed) or captures **ZERO** keyboard events. This is a platform limitation - the Wayland compositor blocks global keyboard event capture for security reasons.

## Why It Doesn't Work

KDE Plasma on Wayland has a different security model than GNOME or X11:
- Compositor filters keyboard events at the Wayland protocol level
- Global keyboard event capture is blocked for privacy/security
- AT-SPI works for other accessibility features but NOT for keyboard sniffing

## Solution Used Instead

The project now uses **evdev** (/dev/input/eventX) for keyboard event capture, which works at a lower level and bypasses compositor restrictions.

## Historical Note

AT-SPI works on X11 and GNOME Wayland, but this is KDE Plasma Wayland specific. The AT-SPI implementation code and test scripts have been removed from the codebase since this approach was abandoned.
