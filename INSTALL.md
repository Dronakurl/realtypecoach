# Installation Instructions for RealTypeCoach

## Quick Start

### 1. Install Dependencies

```bash
sudo apt update
sudo apt install python3-pyatspi at-spi2-core python3-pyqt5
```

### 2. Navigate to Application Directory

```bash
cd /home/konrad/gallery/realtypecoach
```

### 3. Run the Application

```bash
python3 main.py
```

The application will start and appear in your system tray (usually bottom-right corner).

---

## Detailed Installation

### System Dependencies Explained

| Package | Purpose | Required |
|---------|---------|----------|
| `python3-pyatspi` | AT-SPI Python bindings for keyboard monitoring | ✅ Yes |
| `at-spi2-core` | AT-SPI daemon (accessibility framework) | ✅ Yes |
| `python3-pyqt5` | Qt5 GUI framework for system tray | ✅ Yes |

### Verify Installation

```bash
# Check AT-SPI is available
python3 -c "import pyatspi; print('AT-SPI OK')"

# Check PyQt5 is available
python3 -c "from PyQt5.QtWidgets import QApplication; print('PyQt5 OK')"

# Check keyboard layout detection
setxkbmap -query
```

### Enable Accessibility Services

KDE Wayland requires AT-SPI daemon to be running:

```bash
# Check if AT-SPI is running
systemctl --user status at-spi-dbus-bus.service

# If not running, start it
systemctl --user start at-spi-dbus-bus.service

# Enable auto-start on login
systemctl --user enable at-spi-dbus-bus.service
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

### From Source

```bash
# Clone AT-SPI (if package not available)
git clone https://gitlab.gnome.org/GNOME/at-spi2-core.git
cd at-spi2-core
mkdir build && cd build
meson ..
ninja
sudo ninja install
```

### Python AT-SPI Bindings

```bash
# If python3-pyatspi not available in your distro
pip3 install python3-pyatspi
```

---

## Verifying Installation

### Test Keyboard Detection

Run this test script:

```python
#!/usr/bin/env python3
import pyatspi
from PyQt5.QtWidgets import QApplication

print("✅ AT-SPI available")
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

### Problem: "ModuleNotFoundError: No module named 'pyatspi'"

**Solution**: Install python3-pyatspi:
```bash
sudo apt install python3-pyatspi
```

### Problem: "AT-SPI connection failed"

**Solution**: Start AT-SPI daemon:
```bash
systemctl --user start at-spi-dbus-bus.service
```

### Problem: "No keyboard events detected"

**Solutions**:

1. Enable accessibility in KDE:
   - System Settings → Accessibility → Enable assistive technologies

2. Check permissions:
   ```bash
   # Ensure user is in input group
   groups $USER | grep input
   ```

3. Verify AT-SPI is receiving events:
   ```bash
   # Monitor AT-SPI events
   dbus-monitor --session "type='signal',interface='org.a11y.atspi.Event'"
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
sudo apt remove python3-pyatspi python3-pyqt5
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
