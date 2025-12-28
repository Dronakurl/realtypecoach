# KDE Plasma 6.5.2 Wayland Keyboard Event Capture Configuration

## Problem

RealTypeCoach uses AT-SPI to capture keyboard events, but registration returns `False` and no events are captured on KDE Plasma 6.5.2 Wayland.

## Configuration Files to Check

### 1. `~/.config/kdeglobals`

This is KDE's global configuration file. Look for:

```ini
[Accessibility]
# Any accessibility-related settings
```

### 2. `~/.config/plasma-workspace.conf`

Workspace-specific configuration. May contain accessibility settings.

### 3. `~/.config/katerc`

Kate editor configuration - may have accessibility settings.

### 4. `~/.config/kwinrc`

KWin compositor configuration. May have accessibility restrictions.

## Settings to Enable

### Option 1: Accessibility in KDE System Settings

Open: `systemsettings`

Navigate to and enable:
- **Workspace Behavior** → **Accessibility** (if exists)
- **System Settings** → **Accessibility** (main category)
- Look for any "Enable" or "Activate" buttons

### Option 2: Keyboard Accessibility

In System Settings, check:
- **Input Devices** → **Keyboard**
- Look for accessibility options or "Enable AT-SPI" toggle

### Option 3: Check for Existing Keyboard Accessibility Settings

Run:
```bash
grep -i "accessibility\|keyboard\|atspi" ~/.config/kdeglobals
grep -i "accessibility\|keyboard\|atspi" ~/.config/plasma-workspace.conf
grep -i "accessibility\|keyboard\|atspi" ~/.config/kwinrc
```

### Option 4: Test with X11 Backend

Some KDE Plasma setups allow switching between Wayland and X11:

1. Log out of current session
2. At login screen, click "Session" menu
3. Look for "Plasma (X11)" or "Plasma X11" option
4. If available, login with X11 session
5. Test if keyboard events work

If keyboard events work on X11 but NOT on Wayland, the issue is definitely Wayland-specific.

## Known KDE Plasma Wayland Limitations

### Keyboard Event Blocking

KDE Plasma on Wayland may block global keyboard event capture for security/privacy reasons. This affects AT-SPI-based applications that need to capture all keyboard events system-wide.

### Potential Workarounds

1. **Use application-level accessibility**:
   - Configure RealTypeCoach as an accessibility application in KDE
   - This may bypass some Wayland restrictions

2. **Check compositor plugins**:
   - Some plugins may affect accessibility routing
   - Temporarily disable to test

3. **Investigate KDE Plasma version**:
   - Check if newer version has better Wayland AT-SPI support
   - Report issue to KDE bug tracker if needed

## Testing Commands

### Check Current Settings

```bash
# Check for accessibility settings
grep -Ri "accessibility" ~/.config/

# Check AT-SPI services
qdbus --session org.a11y.atspi.Registry
```

### Enable Accessibility Services

```bash
# Ensure AT-SPI D-Bus is running
systemctl --user status at-spi-dbus-bus.service

# Start if not running
systemctl --user start at-spi-dbus-bus.service
```

## Documentation

- [KDE Plasma Wayland](https://docs.kde.org/stable/en/plasma-desktop/plasma-wayland/)
- [KDE Accessibility](https://docs.kde.org/stable/en/plasma-desktop/accessibility-kde/)

## Current Status

- KDE Version: 6.5.2
- Display Server: Wayland
- AT-SPI Service: Running (confirmed)
- Keyboard Events to AT-SPI: **BLOCKED**
- Application Status: Code correct, platform blocking events
