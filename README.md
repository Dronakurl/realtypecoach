<div align="center">

<img src="icons/icon.svg" alt="RealTypeCoach Logo" width="128"/>

# RealTypeCoach

**Track, analyze, and improve your typing on KDE Wayland**

</div>

## Features

- ⌨️ **Global keyboard monitoring** - Tracks typing patterns using [evdev](https://python-evdev.readthedocs.io/)
- 📈 **Progress tracking** - Beautiful charts show your improvement over time
- 🔤 **Word analysis** - Discover which words slow you down
- 🎯 **Personalized insights** - Identifies your slowest keys to help you improve

> [!WARNING]
> The database at `~/.local/share/realtypecoach/typing_data.db` contains all your keystrokes. Do not share it with anyone.

## Requirements

- **OS**: Ubuntu 24.04+ or Debian-based Linux with KDE Plasma
- **Display**: Wayland session
- **Python**: 3.10 or higher

## Installation

**Requirements**: Ubuntu 24.04+, Wayland, Python 3.10+

```bash
# 1. Install dependencies
sudo apt install python3-pyqt5
pip install evdev --user

# 2. Add user to input group (required for keyboard access)
sudo usermod -aG input $USER
# Log out and log back in

# 3. Install the application
./install.sh
```

The install script creates a launcher icon and installs RealTypeCoach to `~/.local/share/realtypecoach/`.

> [!NOTE]
> After installation, the source checkout folder can be safely removed.

### Quick test (run without installing)

```bash
python3 main.py
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

## Uninstallation

```bash
./uninstall.sh
```

To also remove your typing data:

```bash
rm -rf ~/.local/share/realtypecoach
```
