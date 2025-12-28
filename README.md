# RealTypeCoach

RealTypeCoach is a KDE Wayland typing analysis application that monitors keyboard events, analyzes typing patterns, and provides detailed statistics about your typing speed and habits.

## Features

- **Global keyboard monitoring** using evdev (/dev/input/eventX)
- **Automatic keyboard layout detection** (supports US and German layouts)
- **Per-key timing analysis** - identify your slowest keys
- **Burst detection** - tracks continuous typing periods
- **High score tracking** - record your fastest typing bursts (≥10 seconds)
- **Daily statistics** - notification at 18:00 with your daily typing summary
- **Exceptional notifications** - alerts when you achieve a personal best
- **System tray integration** - minimal UI, runs in background
- **Privacy-first design** - only stores keycodes, never actual text or passwords
- **Configurable** - adjust burst timeout, notification thresholds, etc.

## Requirements

- KDE Plasma on Wayland (or X11)
- Python 3.10+
- Ubuntu/Debian-based Linux
- User must be in `input` group

## Installation

### 1. Install System Dependencies

```bash
sudo apt install python3-pyqt5
pip install evdev --user
```

### 2. Add User to Input Group

```bash
sudo usermod -aG input $USER
# Log out and log back in for this to take effect
```

### 3. Clone or Download

```bash
cd /home/konrad/gallery/realtypecoach
```

### 4. Run

```bash
python3 main.py
```

That's it! The application will start and appear in your system tray.

### 5. Development Workflow (Optional)

For easier development, use the `justfile`:

```bash
# List all available commands
just

# Run the application
just run

# Stop all instances
just kill

# Check running status
just status

# Clean and rebuild
just rebuild

# Full reset (kill, clean, reset db, run)
just full

# Test imports
just test-imports
```

Install `just` from: https://just.systems/

## Usage

### System Tray Controls

- **Left-click tray icon**: Show real-time statistics
- **Right-click tray icon**: Menu with options:
  - Show Statistics
  - Pause/Resume Monitoring
  - Settings
  - Quit

### Statistics Panel

Shows:
- Current typing speed (WPM)
- Top 10 slowest keys
- Today's typing time
- Today's personal best WPM

### Settings

Configurable options:
- Burst timeout (default: 3 seconds)
- High score minimum duration (default: 10 seconds)
- Exceptional WPM threshold (default: 120 WPM)
- Password field exclusion (default: enabled)
- Notifications enabled (default: yes)
- Number of slowest keys to display (default: 10)
- Data retention period (default: 90 days)
- Keyboard layout (default: auto-detect)

## Notifications

### Exceptional Bursts

You'll receive a desktop notification when:
- You achieve a personal best typing speed (bursts ≥10 seconds)
- Your typing speed exceeds 120 WPM

### Daily Summary (18:00)

Every day at 18:00, you'll receive a summary:
- Total keystrokes today
- Total typing time
- Average WPM
- Slowest key today
- Personal best if achieved

## Privacy

### What IS Stored

- Linux keycodes (e.g., 30 for 'a', 48 for 'b')
- Timestamps (milliseconds since epoch)
- Event types (press/release)
- Application names
- Burst metadata

### What is NOT Stored

- **No actual typed text** - we never reconstruct what you typed
- **No passwords** - password fields are automatically excluded
- **No sensitive sequences** - only keycodes and timing data

### Data Location

All data is stored locally in:
```
~/.local/share/realtypecoach/typing_data.db
```

You can view, export, or delete this data at any time.

## Export Data

Export your typing statistics to CSV via Settings → Export to CSV.

CSV format:
```csv
timestamp_ms,keycode,key_name,event_type,app_name,is_password_field
```

## Keyboard Layouts

Currently supported:
- US (QWERTY)
- German (QWERTZ)

Your layout is automatically detected and switches are tracked in real-time.

## Troubleshooting

### Application Won't Start

Ensure evdev is installed:
```bash
python3 -c "import evdev; print('evdev OK')"
```

### No Keyboard Events Detected

1. Ensure user is in `input` group:
   ```bash
   groups $USER | grep input
   ```

2. If not in input group, add user:
   ```bash
   sudo usermod -aG input $USER
   # Log out and log back in
   ```

3. List available input devices:
   ```bash
   python3 -c "from evdev import list_devices; print(list_devices())"
   ```

### Layout Not Detected

The application defaults to US layout if auto-detection fails. You can manually set the layout in Settings.

## License

GPLv3

## Contributing

This is a personal project focused on typing analysis for personal improvement. Feel free to fork and adapt for your needs!
