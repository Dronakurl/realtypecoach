# CPU Usage Investigation

**Status:** RESOLVED (2026-01-28)

Two high-CPU issues were identified and fixed:

## Issue 1: Qt isVisible() Call from Background Thread (FIXED)

**Problem:** Calling `stats_panel.isVisible()` (Qt method) from the background event listener thread caused high CPU usage.

**Solution:** Replaced with thread-safe `self._stats_panel_visible` flag.

**Implementation:**
- `main.py:106` - Flag declaration
- `main.py:247` - Passed to EvdevHandler via lambda
- `main.py:397` - `set_stats_panel_visibility()` method
- `core/evdev_handler.py:152-158` - `set_stats_panel_visible()` method

## Issue 2: Device Disconnection Busy Loop (FIXED)

**Problem:** When a Bluetooth keyboard disconnected, the bad file descriptor caused `select()` to return immediately, creating an infinite loop.

**Solution:** Added device validation and cleanup before `select()`.

**Details:** See [Device Disconnection Busy Loop Fix](./issues/device-disconnection-busy-loop-fix.md)

## Other Investigated Areas (Not Issues)

These areas were investigated but found to NOT be causing issues:

1. **Smoothing algorithm** - Only runs on-demand (tab view, slider change), not on every burst
2. **Database encryption** - SQLCipher overhead acceptable with connection pooling
3. **pyqtgraph rendering** - Auto-range configuration correct
4. **ThreadPoolExecutor** - Limited to 2 workers, only for slider changes

## Files Modified

- `main.py` - Thread-safe visibility flag
- `core/evdev_handler.py` - Device validation, visibility flag support
- `tests/test_evdev_handler.py` - Device error handling tests
