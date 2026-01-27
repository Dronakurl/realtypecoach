# Fix: High CPU Usage from Disconnected evdev Device

**Date:** 2026-01-28
**Status:** FIXED
**Related:** [CPU Usage Investigation](../cpu-usage-investigation.md)

## Problem Summary

**Root Cause:** Thread consuming 20% CPU due to infinite busy loop when a Bluetooth keyboard device disconnects.

**Perpetrator:** `core/evdev_handler.py:147-183` - Device disconnection creates infinite loop

### The Issue

When a device disconnects (e.g., Bluetooth keyboard removed):
1. Device's file descriptor remains in the `devices` list
2. `select()` returns immediately when given a bad/closed file descriptor
3. The `try/except OSError` block catches errors but uses `continue` - loop repeats forever
4. The busy-loop prevention only triggers when `r` is empty, but here `r` contains the bad device

### Evidence from Logs

```
2026-01-27 10:28:39,095 - realtypecoach.evdev - DEBUG - Device read error: [Errno 19] No such device
```

Thread 543965: 1.6M CPU centiseconds, State=R (running), WCHAN=0

## Solution: Remove Bad File Descriptors from Devices List

### Changes Made

#### 1. Added helper methods (`core/evdev_handler.py:246-289`)

**`_is_device_valid(device) -> bool`**
- Checks if a device file descriptor is still valid
- Uses `fcntl.fcntl(fd, fcntl.F_GETFL)` to validate FD
- Returns `False` if `OSError` or `AttributeError` is raised

**`_remove_bad_devices(devices: list, error: OSError) -> list`**
- Filters out invalid devices from the list
- Logs which devices were removed
- Closes bad devices safely
- Updates `self.devices` for consistency

#### 2. Updated main event loop (`core/evdev_handler.py:147-212`)

**Before each `select()` call:**
```python
# Filter out any bad devices before select
valid_devices = [d for d in devices if self._is_device_valid(d)]
if len(valid_devices) < len(devices):
    log.warning(f"Removed {len(devices) - len(valid_devices)} invalid device(s)")
    devices = valid_devices
    self.devices = devices

# Check if we still have devices
if not devices:
    log.error("No valid devices remaining, exiting listener thread")
    return
```

**Wrapped `select()` in try/except:**
```python
try:
    r, _, _ = select(devices, [], [], timeout)
except OSError as e:
    # select() failed - likely bad file descriptor
    log.error(f"select() failed: {e}, attempting to recover")
    # Find and remove bad device
    devices = self._remove_bad_devices(devices, e)
    continue  # Retry with cleaned device list
```

**Fixed device read error handling:**
```python
except OSError as e:
    # Device disconnected or error - remove it from list
    log.warning(
        f"Device {device.name} at {device.path} failed: {e}, removing from device list"
    )
    if device in devices:
        devices.remove(device)
    # Close the bad device
    try:
        device.close()
    except Exception:
        pass
    continue
```

### What Changed

| Aspect | Before | After |
|--------|--------|-------|
| Bad devices in list | Stay forever, causing busy loop | Removed before `select()` |
| `select()` OSError | Not handled, could crash | Caught, devices filtered, retry |
| Device read OSError | Logged with `continue` | Device removed and closed |
| No devices remaining | Infinite loop | Clean exit with log message |

## Testing

Added new test class `TestDeviceErrorHandling` in `tests/test_evdev_handler.py`:

1. **`test_is_device_valid_with_good_device`** - Validates good devices
2. **`test_is_device_valid_with_bad_device`** - Rejects devices with bad FD
3. **`test_remove_bad_devices_filters_invalid`** - Multiple devices, one bad
4. **`test_device_read_oserror_removes_device`** - Read error removes device
5. **`test_select_error_with_bad_fd`** - `select()` OSError recovery
6. **`test_multiple_devices_one_fails`** - One device fails, others continue

## Verification

To test with a real device disconnect:

```bash
# Run the application
python main.py

# In another terminal, monitor CPU
watch -n 1 'ps -p $(pgrep -f realtypecoach) -o pid,pcpu,tid'

# Disconnect/reconnect Bluetooth keyboard
# Verify CPU drops back to < 2% after disconnect
```

Check logs for device removal:
```bash
tail -f ~/.local/state/realtypecoach/realtypecoach.log | grep -E "remov|device|Device"
```

## Related Files

- `core/evdev_handler.py:246-289` - Helper methods `_is_device_valid()`, `_remove_bad_devices()`
- `core/evdev_handler.py:147-212` - Main event loop with error handling
- `tests/test_evdev_handler.py:495-695` - Device error handling tests
