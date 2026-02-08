# RealTypeCoach Development Commands

# Running
# Sync dependencies and run the application
run:
    @just sync-deps
    @bash ./kill.sh 2>/dev/null || true
    @.venv/bin/python3 main.py

# Install/sync dependencies from pyproject.toml
sync-deps:
    bash -c 'if [ ! -d ".venv" ]; then uv venv --python 3.14.2 .venv; fi && .venv/bin/python3 -m pip install -e .'

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

# Monitor CPU usage over 5 seconds
monitor-cpu:
    #!/usr/bin/env bash
    pid=$(ps aux | grep "main.py" | grep -v grep | awk '$11 ~ /python3$/ {print $2}' | head -n 1)
    if [ -z "$pid" ]; then
        echo "RealTypeCoach is not running"
        exit 1
    fi
    echo "Monitoring CPU usage for PID $pid over 5 seconds..."
    echo ""
    total=0
    count=0
    for i in {1..5}; do
        cpu=$(pidstat -p "$pid" 1 1 | tail -n +4 | head -n -1 | awk '{print $8}' | tr ',' '.')
        echo "  Sample $i: ${cpu}%"
        if [ -n "$cpu" ]; then
            total=$(echo "$total + $cpu" | LC_ALL=C bc)
            ((count++))
        fi
    done
    echo ""
    if [ $count -gt 0 ]; then
        avg=$(echo "scale=2; $total / $count" | LC_ALL=C bc)
        echo "Average CPU usage (last 5s): ${avg}%"
    fi
    lifetime_avg=$(ps -p "$pid" -o %cpu --no-headers | tr -d ' ')
    echo "Lifetime average CPU usage: ${lifetime_avg}% (average since process start)"

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

# Name Management
# Add a single name to the common names list
add-name NAME:
    @python3 core/add_names.py {{NAME}}

# Add names from a file to the common names list
add-names-from-file FILE:
    @python3 core/add_names.py --file {{FILE}}

# Sort and deduplicate names in names.txt
sort-names:
    @python3 core/add_names.py --sort-only

# Check total count of names
check-names:
    @python3 -c "from core.common_names import COMMON_NAMES; print(f'Total names: {sum(len(s) for s in COMMON_NAMES.values())} (including genitive forms)')"

# PostgreSQL Sync
# Sync local SQLite with remote PostgreSQL
sync:
    @.venv/bin/python3 scripts/sync.py

# Compare local and remote database statistics
compare-stats user_id="":
    @if [ -n "{{user_id}}" ]; then \
        .venv/bin/python3 scripts/compare_stats.py --user-id {{user_id}}; \
    else \
        .venv/bin/python3 scripts/compare_stats.py; \
    fi

# Show local database statistics
local-stats user_id="":
    @if [ -n "{{user_id}}" ]; then \
        .venv/bin/python3 scripts/local_stats.py --user-id {{user_id}}; \
    else \
        .venv/bin/python3 scripts/local_stats.py; \
    fi

# Show remote database statistics
remote-stats user_id="":
    @if [ -n "{{user_id}}" ]; then \
        .venv/bin/python3 scripts/remote_stats.py --user-id {{user_id}}; \
    else \
        .venv/bin/python3 scripts/remote_stats.py; \
    fi

# Correct inflated statistics in remote database
tmp-correct-stats user_id="":
    @.venv/bin/python3 scripts/correct_stats.py {{user_id}}

# Correct inflated statistics in remote database (dry run)
tmp-correct-stats-dry user_id="":
    @.venv/bin/python3 scripts/correct_stats.py --dry-run {{user_id}}

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

# Ollama Text Generation
# Test Ollama text generation with a prompt
ollama-test prompt:
    .venv/bin/python3 scripts/ollama_test.py "{{prompt}}"

# Start Ollama service
start-ollama:
    bash ./scripts/start_ollama.sh

# Database Migrations
# Create a new migration with descriptive name
migrate-create name:
    @.venv/bin/alembic revision -m "{{name}}"

# Run database migrations to latest version
migrate-upgrade:
    @echo "Running database migrations..."
    @.venv/bin/python3 -c "from pathlib import Path; from utils.crypto import CryptoManager; from core.sqlite_migration_runner import SQLiteMigrationRunner; db = Path.home() / '.local/share/realtypecoach/typing_data.db'; crypto = CryptoManager(db); migration_dir = Path.cwd() / 'migrations'; runner = SQLiteMigrationRunner(db, migration_dir); print(f'Current version: {runner.get_current_version() or \"none\"}'); runner.upgrade(); print(f'New version: {runner.get_current_version()}')"

# Show current database migration version
migrate-status:
    @echo "Current database migration version:"
    @.venv/bin/alembic current 2>/dev/null || echo "Alembic not initialized or database not found"

# Show migration history
migrate-history:
    @.venv/bin/alembic history
