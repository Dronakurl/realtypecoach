# Fix: High CPU Usage from Disconnected evdev Device

**Date:** 2026-01-28
**Status:** FIXED

## Problem

When a Bluetooth keyboard disconnected, a bad file descriptor caused `select()` to return immediately, creating an infinite busy loop using ~20% CPU.

**Evidence:** Log entry `[Errno 19] No such device` with thread State=R (running), WCHAN=0.

## Solution

Added device validation and cleanup to remove bad file descriptors from the devices list.

### Changes Made

**Helper methods** (`core/evdev_handler.py:319-376`):

- `_is_device_valid(device)` - Checks FD validity using `fcntl.fcntl(fd, F_GETFL)`
- `_remove_bad_devices(devices, error)` - Filters, logs, and closes bad devices

**Main event loop** (`core/evdev_handler.py:182-211`):

```python
# Filter bad devices before select
valid_devices = [d for d in devices if self._is_device_valid(d)]
if len(valid_devices) < len(devices):
    devices = valid_devices
    self.devices = devices

if not devices:
    log.error("No valid devices remaining, exiting")
    return

try:
    r, _, _ = select(devices, [], [], timeout)
except OSError as e:
    devices = self._remove_bad_devices(devices, e)
    continue  # Retry with cleaned list
```

**Device read error handling** (`core/evdev_handler.py:243-255`):

```python
except OSError as e:
    if device in devices:
        devices.remove(device)
    device.close()  # Safely close bad device
    continue
```

## Testing

Added `TestDeviceErrorHandling` in `tests/test_evdev_handler.py` with 6 test cases:
- Device validation
- Bad device filtering
- Read error handling
- select() OSError recovery
- Multiple device scenarios

## Verification

```bash
# Monitor CPU during disconnect
watch -n 1 'ps -p $(pgrep -f realtypecoach) -o pid,pcpu,tid'

# Check logs
tail -f ~/.local/state/realtypecoach/realtypecoach.log | grep -i remov
```

CPU should drop back to <2% after device disconnect.
