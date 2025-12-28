# Installation Instructions for RealTypeCoach

## Quick Start

### 1. Install Dependencies

```bash
sudo apt update
sudo apt install python3-pyqt5
pip install evdev --user
```

### 2. Add User to Input Group

```bash
sudo usermod -aG input $USER
# Log out and log back in for this to take effect
```

### 3. Navigate to Application Directory

```bash
cd /home/konrad/gallery/realtypecoach
```

### 4. Run the Application

```bash
python3 main.py
```

The application will start and appear in your system tray (usually bottom-right corner).

---

## Detailed Installation

### System Dependencies Explained

| Package | Purpose | Required |
|---------|---------|----------|
| `python3-pyqt5` | Qt5 GUI framework for system tray | ✅ Yes |
| `evdev` | Python bindings for reading /dev/input/eventX | ✅ Yes |

### Verify Installation

```bash
# Check PyQt5 is available
python3 -c "from PyQt5.QtWidgets import QApplication; print('PyQt5 OK')"

# Check evdev is available
python3 -c "import evdev; print('evdev OK')"

# Check keyboard layout detection
setxkbmap -query
```

### Check Input Device Access

```bash
# List available input devices
python3 -c "from evdev import list_devices; print(list_devices())"

# Verify you can read keyboard events (requires input group)
ls -l /dev/input/by-path/
```

---

## First Run

### What to Expect

1. **System Tray Icon**: A keyboard icon will appear in your system tray
2. **No Window**: The application runs in background, no main window
3. **Status Indication**: Icon changes color based on state:
   - Blue = Monitoring active
   - Orange = Monitoring paused

### Initial Setup

The application will automatically:
- Create data directory: `~/.local/share/realtypecoach/`
- Create database: `typing_data.db`
- Detect your current keyboard layout
- Load default settings

### First Typing Session

Start typing in any application (terminal, editor, browser). The application will:
- Capture each keypress (not actual text, just keycodes)
- Detect bursts of continuous typing
- Track statistics in real-time

### View Statistics

Left-click the system tray icon to see real-time statistics:
- Current WPM (words per minute)
- Top 10 slowest keys
- Today's typing time
- Today's personal best

---

## Manual Installation (If apt Fails)

### Python evdev from pip

```bash
pip3 install evdev --user
```

---

## Verifying Installation

### Test Keyboard Detection

Run this test script:

```python
#!/usr/bin/env python3
import evdev
from PyQt5.QtWidgets import QApplication

print("✅ evdev available")
print("✅ PyQt5 available")

app = QApplication([])
print("✅ Qt initialized")

print("\nAll dependencies verified!")
```

Save as `test_deps.py` and run:
```bash
python3 test_deps.py
```

### Test Layout Detection

```bash
# Test your current layout detection
python3 -c "from utils.keyboard_detector import get_current_layout; print(get_current_layout())"
```

---

## Troubleshooting

### Problem: "ModuleNotFoundError: No module named 'evdev'"

**Solution**: Install evdev:
```bash
pip install evdev --user
```

### Problem: "Permission denied: /dev/input/eventX"

**Solution**: Add user to input group:
```bash
sudo usermod -aG input $USER
# Log out and log back in for this to take effect
```

### Problem: "No keyboard events detected"

**Solutions**:

1. Check permissions:
   ```bash
   # Ensure user is in input group
   groups $USER | grep input
   ```

2. List available input devices:
   ```bash
   python3 -c "from evdev import list_devices; print(list_devices())"
   ```

### Problem: Icon not visible in system tray

**Solutions**:

1. Check KDE settings:
   - System Settings → Workspace Behavior → System Tray → Ensure hidden icons can be shown

2. Try showing system tray:
   - Right-click panel → Edit Panel → Add Widgets → System Tray

### Problem: Application crashes on startup

**Solution**: Run with verbose output:
```bash
python3 main.py --verbose
```

Check for error messages and report issues.

---

## Uninstallation

### Remove Application

```bash
# Remove application directory
rm -rf /home/konrad/gallery/realtypecoach

# Remove data (if desired)
rm -rf ~/.local/share/realtypecoach
```

### Remove Dependencies (Optional)

```bash
# Only remove if no other applications need them
sudo apt remove python3-pyqt5
pip uninstall evdev
```

---

## System Requirements

- **OS**: Ubuntu 24.04+ or Debian-based Linux with KDE Plasma
- **Display**: Wayland session
- **Python**: 3.10 or higher
- **RAM**: Minimal (application uses <50MB)
- **Disk**: <10MB for data (depending on usage history)

---

## Next Steps

After installation:

1. ✅ Start typing naturally in your daily workflow
2. ✅ Check statistics panel after typing sessions
3. ✅ Adjust settings to your preferences
4. ✅ Watch for daily 18:00 statistics notifications
5. ✅ Work on your slowest keys!

Enjoy improved typing awareness! 🚀
