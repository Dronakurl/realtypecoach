<div align="center">

# RealTypeCoach

**A KDE Wayland typing analysis application that monitors keyboard events and provides detailed statistics about your typing speed and habits.**

</div>

## Features

- ⌨️ **Global keyboard monitoring** - Tracks typing patterns using evdev
- 📊 **Detailed statistics** - Per-key timing analysis, burst detection, and daily summaries
- 🔒 **Privacy-first** - Only stores keycodes, never actual text or passwords
- 🎯 **Personalized insights** - Identifies your slowest keys to help you improve

> **Warning:** The database at `~/.local/share/realtypecoach/typing_data.db` contains all your keystrokes. Do not share it with anyone.

## Requirements

- **OS**: Ubuntu 24.04+ or Debian-based Linux with KDE Plasma
- **Display**: Wayland session
- **Python**: 3.10 or higher

## Installation

### Quick Start

```bash
# 1. Install system dependencies
sudo apt install python3-pyqt5
pip install evdev --user

# 2. Add user to input group (required for reading keyboard events)
sudo usermod -aG input $USER
# Log out and log back in for this to take effect

# 3. Clone and navigate to the application directory
cd ~/realtypecoach

# 4. Run the application
python3 main.py
```

The application will start and appear in your system tray.

### System Dependencies

| Package | Purpose | Installation |
|---------|---------|--------------|
| `python3-pyqt5` | Qt5 GUI framework for system tray | `sudo apt install python3-pyqt5` |
| `evdev` | Python bindings for reading /dev/input/eventX | `pip install evdev --user` |

### Optional: Install with Launcher

To install RealTypeCoach with an application launcher icon:

```bash
./install.sh
```

This will:
- Copy application files to `~/.local/share/realtypecoach/`
- Create a wrapper script at `~/.local/bin/realtypecoach`
- Add a desktop entry for your application launcher
- Generate required icons

After installation, you can launch RealTypeCoach from your application menu or by typing `realtypecoach`.

### Verify Installation

```bash
# Check PyQt5 is available
python3 -c "from PyQt5.QtWidgets import QApplication; print('PyQt5 OK')"

# Check evdev is available
python3 -c "import evdev; print('evdev OK')"

# Verify keyboard layout detection
setxkbmap -query
```

## Usage

The application runs in your system tray:

### System Tray Icon

- **Blue icon**: Monitoring active
- **Orange icon**: Monitoring paused

### Controls

- **Left-click**: Show real-time statistics (current WPM, slowest keys, today's stats)
- **Right-click**: Menu with options
  - Show Statistics
  - Pause/Resume monitoring
  - Settings (burst filter, notification preferences)
  - Quit

### How It Works

1. RealTypeCoach captures keyboard events from `/dev/input/eventX` devices
2. It detects bursts of continuous typing (separated by pauses)
3. Only keycodes and timings are stored - never actual text or passwords
4. Statistics are calculated per-key and per-burst
5. Daily summary notifications are sent at 18:00

## Troubleshooting

### "ModuleNotFoundError: No module named 'evdev'"

Install evdev:
```bash
pip install evdev --user
```

### "Permission denied: /dev/input/eventX"

Add your user to the input group:
```bash
sudo usermod -aG input $USER
# Log out and log back in for this to take effect
```

### "No keyboard events detected"

1. Check that you're in the input group:
   ```bash
   groups $USER | grep input
   ```

2. List available input devices:
   ```bash
   python3 -c "from evdev import list_devices; print(list_devices())"
   ```

### Icon not visible in system tray

1. Check KDE settings:
   - System Settings → Workspace Behavior → System Tray → Ensure hidden icons can be shown

2. Add system tray to panel:
   - Right-click panel → Edit Panel → Add Widgets → System Tray

## Uninstallation

### Remove launcher installation

```bash
./uninstall.sh
```

### Remove manually

```bash
# Remove application directory
rm -rf ~/realtypecoach

# Remove data (if desired)
rm -rf ~/.local/share/realtypecoach

# Remove dependencies (optional, only if no other apps need them)
sudo apt remove python3-pyqt5
pip uninstall evdev
```
