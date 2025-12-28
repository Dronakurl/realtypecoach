# Dependencies Installation for RealTypeCoach

## Required System Packages

The application requires **one** additional system package (PyQt5 should already be installed):

```bash
sudo apt update
sudo apt install python3-pyatspi
```

That's it!

---

## Verify Installation

After installation, verify all dependencies are available:

```bash
# Check pyatspi
python3 -c "import pyatspi; print('✓ pyatspi OK')"

# Check PyQt5
python3 -c "from PyQt5.QtWidgets import QApplication; print('✓ PyQt5 OK')"

# Check database support
python3 -c "import sqlite3; print('✓ SQLite OK')"
```

Expected output:
```
✓ pyatspi OK
✓ PyQt5 OK
✓ SQLite OK
```

---

## What Each Package Does

| Package | Purpose |
|---------|----------|
| `python3-pyatspi` | AT-SPI Python bindings for monitoring keyboard events (required) |
| `python3-pyqt5` | Qt5 GUI framework for system tray (likely already installed) |
| `sqlite3` | Database (built into Python) |

---

## Already Installed

These packages are already on your system:
- ✅ `at-spi2-core` - AT-SPI D-Bus core service
- ✅ `at-spi2-common` - AT-SPI common files
- ✅ `libatk-bridge2.0` - AT-SPI toolkit bridge

You only need to install the Python bindings.

---

## Troubleshooting

### Problem: "Unable to locate package python3-pyatspi"

**Solution**: Update package lists:
```bash
sudo apt update
sudo apt search python3-pyatspi
```

### Problem: "ModuleNotFoundError: No module named 'pyatspi'"

**Solution**: Reinstall the package:
```bash
sudo apt install --reinstall python3-pyatspi
```

### Problem: AT-SPI daemon not running

**Solution**: Start AT-SPI service:
```bash
systemctl --user status at-spi-dbus-bus.service
systemctl --user start at-spi-dbus-bus.service
```

---

## After Installation

Once installed, you can run RealTypeCoach:

```bash
cd /home/konrad/gallery/realtypecoach
python3 main.py
```

The application will start and appear in your system tray!
