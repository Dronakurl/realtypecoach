<div align="center">

<img src="icons/icon.svg" alt="RealTypeCoach Logo" width="128"/>

# RealTypeCoach

**Passive typing analytics that identify your slowest keys and words—no practice tests required**

Unlike artificial typing tests, RealTypeCoach analyzes your real-world typing to pinpoint exactly what's slowing you down. See your WPM progress over time, discover which words cost you the most speed, and track your personal bests—all while working normally.

[![Screenshot](screenshot.png)](screenshot.png)

</div>

## Features

- 📊 **Real-world analytics** - Learn from your actual typing, not artificial exercises
- 🎯 **Identify bottlenecks** - See your slowest keys and words at a glance
- 🔒 **Privacy-first** - Encrypted local storage, zero keystroke logging
- 📈 **Track progress** - Monitor WPM improvement and personal bests over time
- ⚡ **Zero distraction** - Runs silently in your system tray
- 🧠 **Data-driven insights** - Know exactly what to practice for maximum impact

## Requirements

- **Tested on**: Ubuntu 24.04+ on Wayland (works on KDE Plasma, XFCE, and other Linux desktops)
- **Python**: 3.10 or higher

See [CONTRIBUTING.md](CONTRIBUTING.md) for compatibility reports.

## Installation

```bash
# 0. Clone or download this repository to a folder
git clone https://github.com/yourusername/realtypecoach.git
cd realtypecoach

# 1. Add your user to the input group (required for keyboard access)
sudo usermod -aG input $USER
# Log out and log back in for this to take effect

# 2. After logging back in, run the installation script
./install.sh
```

The install script installs RealTypeCoach to your home directory (in `~/.local/share/realtypecoach/`) and creates an entry in your application menu. You can delete the code checkout after installation.

> [!NOTE]
> **Why the `input` group?** RealTypeCoach needs to read your keyboard events to analyze typing. Linux restricts this to the `input` group for security. On single-user systems (your laptop/desktop), this is safe and appropriate.

## Usage

The application runs in your system tray:

### System Tray Icon

- **Blue icon**: Monitoring active
- **Orange icon**: Monitoring paused

### Controls

- **Left-click**: Show real-time statistics (current WPM, slowest keys, today's stats)
- **Right-click**: Menu with options
  - Show Statistics
  - Practice (Digraphs, Words, Clipboard, AI)
  - Pause/Resume monitoring
  - Settings (burst filter, notification preferences)
  - Quit

> **Note**: The practice feature opens [Monkeytype](https://monkeytype.com) in your browser—a minimal, customizable typing test website. Custom text from your statistics is loaded automatically for focused practice sessions.

### How It Works

1. RealTypeCoach captures keyboard events from `/dev/input/eventX` devices
2. Keystrokes are processed in real-time to detect bursts of continuous typing
3. Only aggregated statistics are stored (WPM, key speeds, word speeds) - **no keystroke history**
4. Statistics are calculated per-key and per-word to identify your slowest patterns
5. Optional daily summary notifications at a configurable time

## Troubleshooting


### "Permission denied: /dev/input/eventX"

Add your user to the input group as notes in the instructions for installation.

### "No keyboard events detected"

1. Check that you're in the input group:

   ```bash
   groups $USER | grep input
   ```

2. List available input devices:

   ```bash
   .venv/bin/python3 -c "from evdev import list_devices; print(list_devices())"
   ```

### "Database encryption key not found"

This error occurs when the keyring cannot access the encryption key. Possible solutions:

1. **Check keyring is unlocked**:

   ```bash
   # For GNOME
   loginctl unlock-session

   # For KDE/KWallet
   kwallet-query -l kdewallet
   ```

2. **Verify keyring backend**:

   ```bash
   python3 -c "import keyring; print(keyring.get_keyring())"
   ```

3. **If all else fails**: Reinitialize (WARNING: This deletes existing data)

   ```bash
   rm ~/.local/share/realtypecoach/typing_data.db
   .venv/bin/python3 -c "from utils.crypto import CryptoManager; from pathlib import Path; c = CryptoManager(Path.home() / '.local' / 'share' / 'realtypecoach' / 'typing_data.db'); c.delete_key()"
   ```

## Uninstallation

```bash
./uninstall.sh
```
This will ask you if you want to keep your data or not.
