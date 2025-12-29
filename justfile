# RealTypeCoach Development Commands

# Running
# Run the application
run:
    @bash ./kill.sh 2>/dev/null || true
    @python3 main.py

# Run and show first 50 lines
watch:
    @just run 2>&1 | head -50

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

# Testing
# Run all Python tests
test-all:
    @python3 -m pytest tests/ -v

# Test Python module imports
test-imports:
    @python3 -c 'import sys; sys.path.insert(0, "."); \
        from core.storage import Storage; \
        from core.burst_detector import BurstDetector; \
        from core.analyzer import Analyzer; \
        from utils.config import Config; \
        from utils.keycodes import get_key_name; \
        from PyQt5.QtWidgets import QApplication; \
        print("✓ All imports successful")'

# Clean, check, and run
rebuild:
    @just clean
    @just check
    @just run

# Full reset, clean, check, and run
full:
    @just reset
    @just clean
    @just check
    @just run

# Git
# Show git status
git-status:
    @git status --short

# Show recent git commits
git-log:
    @git log --oneline -10
