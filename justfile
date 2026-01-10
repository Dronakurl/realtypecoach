# RealTypeCoach Development Commands

# Running
# Sync dependencies and run the application
run:
    @just sync-deps
    @bash ./kill.sh 2>/dev/null || true
    @.venv/bin/python3 main.py

# Install/sync dependencies from pyproject.toml
sync-deps:
    bash -c 'if [ ! -d ".venv" ]; then python3 -m venv .venv; fi && .venv/bin/python3 -m pip install -e .'

# Instance Management
# Kill running instances
kill:
    bash ./kill.sh

# Installation
# Install the application
install:
    bash ./install.sh

# Uninstall the application
uninstall:
    bash ./uninstall.sh

# Check if application is running
status:
    @if pgrep -f "python3.*realtypecoach" > /dev/null; then \
        echo "Running:"; \
        pgrep -f "python3.*realtypecoach" | tr '\n' ' '; \
    else \
        echo "Not running"; \
    fi

# Monitor log file in real-time
monitor-log:
    @tail -f ~/.local/state/realtypecoach/realtypecoach.log

# Testing
# Syntax check Python files
check:
    @python3 -m py_compile main.py
    @echo "Syntax check passed"

# Cleaning
# Clean cache and kill instances
clean:
    @just kill
    @find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    @find . -type f -name "*.pyc" -delete 2>/dev/null || true
    @echo "Cache cleaned"

# Reset the database
reset:
    @just kill
    @rm -f ~/.local/share/realtypecoach/typing_data.db
    @rm -f ~/.local/share/realtypecoach/typing_data.db-shm
    @rm -f ~/.local/share/realtypecoach/typing_data.db-wal
    @echo "Database reset"

# Query encrypted database
db-query query:
    @.venv/bin/python3 scripts/db_query.py "{{query}}"

# Show database schema
db-schema:
    @.venv/bin/python3 scripts/db_query.py --schema

# Show table contents
db-table table limit="10":
    @.venv/bin/python3 scripts/db_query.py --table {{table}} --limit {{limit}}

# Seed database with realistic typing data
seed-database days:
    @.venv/bin/python3 scripts/seed_database.py --days {{days}}

# Testing
# Format code with ruff and remove unused imports
ruff-format:
    @echo "=== Formatting with ruff ==="
    @ruff format .
    @ruff check --fix .

# Run all Python tests
test-all: ruff-format
    @echo "=== Checking Python syntax ==="
    @python3 -m py_compile main.py
    @python3 -m py_compile ui/settings_dialog.py
    @python3 -m py_compile ui/stats_panel.py
    @python3 -m py_compile ui/tray_icon.py
    @python3 -m py_compile ui/typing_time_graph.py
    @python3 -m py_compile ui/wpm_graph.py
    @echo "=== Running pytest ==="
    @.venv/bin/python3 -m pytest tests/ -v

# Test Python module imports
test-imports:
    @.venv/bin/python3 -c 'import sys; sys.path.insert(0, "."); \
        from core.storage import Storage; \
        from core.burst_detector import BurstDetector; \
        from core.analyzer import Analyzer; \
        from utils.config import Config; \
        from utils.keycodes import get_key_name; \
        from PySide6.QtWidgets import QApplication; \
        print("✓ All imports successful")'

# Development Setup
# Setup zellij with claude and shell panes
dev-setup:
    zellij action rename-tab realtypecoach
    zellij action rename-pane shell
    zellij action new-pane --direction right -- claude --dangerously-skip-permissions
    zellij action rename-pane claude
    zellij action focus-previous-pane

# Diagnostic: Test keyboard event capture
test-evdev:
    #!/usr/bin/env python3
    python3 -c '
    import sys
    try:
        from evdev import InputDevice, list_devices, ecodes
    except ImportError:
        print("Error: evdev module not installed. Install with: sudo apt install python3-evdev")
        sys.exit(1)

    print("=" * 50)
    print("evdev Keyboard Event Test")
    print("=" * 50)

    # Find keyboard devices
    print("\nScanning for keyboard devices...")
    keyboards = []
    for path in list_devices():
        try:
            device = InputDevice(path)
            if ecodes.EV_KEY in device.capabilities():
                caps = device.capabilities()[ecodes.EV_KEY]
                has_letter_keys = any(
                    ecodes.KEY_A <= code <= ecodes.KEY_Z or
                    code in [ecodes.KEY_SPACE, ecodes.KEY_ENTER, ecodes.KEY_ESC]
                    for code in caps
                )
                if has_letter_keys:
                    keyboards.append(device)
                    print(f"  ✓ Found keyboard: {device.name} at {path}")
        except PermissionError:
            print(f"  ✗ Permission denied: {path}")
            print("    You need to be in the '\''input'\'' group:")
            print("      sudo usermod -aG input $USER")
            print("    Then log out and log back in.")
            sys.exit(1)
        except OSError as e:
            print(f"  ✗ Error accessing {path}: {e}")

    if not keyboards:
        print("\n✗ No keyboard devices found!")
        sys.exit(1)

    print(f"\n✓ Found {len(keyboards)} keyboard device(s)")
    print("=" * 50)
    print("Start typing to test keyboard event capture...")
    print("Press Ctrl+C to exit")
    print("=" * 50)

    event_count = 0
    try:
        from select import select

        while True:
            r, _, _ = select(keyboards, [], [], 0.1)

            for device in r:
                try:
                    for event in device.read():
                        if event.type == ecodes.EV_KEY:
                            event_count += 1

                            if event.value == 1:  # Press
                                print(f"✓ KEY PRESS: code={event.code}")
                            elif event.value == 0:  # Release
                                print(f"  KEY RELEASE: code={event.code}")

                            if event_count >= 10:
                                print("\n✓ Received 10 keyboard events - evdev is working!")
                                print("Press Ctrl+C to exit")

                except OSError:
                    continue

    except KeyboardInterrupt:
        print(f"\n\nTotal events captured: {event_count}")
        print("✓ Test completed successfully")
        sys.exit(0)

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    '

