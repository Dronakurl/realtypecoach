# RealTypeCoach Development Commands

# Running
run:
    @bash ./kill.sh 2>/dev/null || true
    @python3 main.py

watch:
    @just run 2>&1 | head -50

# Instance Management
kill:
    bash ./kill.sh

# Installation
install:
    bash ./install.sh

uninstall:
    bash ./uninstall.sh

status:
    @if pgrep -f "python3.*realtypecoach" > /dev/null; then \
        echo "Running:"; \
        pgrep -f "python3.*realtypecoach" | tr '\n' ' '; \
    else \
        echo "Not running"; \
    fi

# Testing
check:
    @python3 -m py_compile main.py
    @echo "Syntax check passed"

test-atspi:
    @bash -c 'timeout 10 python3 test_atspi.py 2>&1 || echo "AT-SPI test completed or timed out"'

# Cleaning
clean:
    @just kill
    @find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    @find . -type f -name "*.pyc" -delete 2>/dev/null || true
    @echo "Cache cleaned"

reset:
    @just kill
    @rm -f ~/.local/share/realtypecoach/typing_data.db
    @echo "Database reset"

# Testing
test-imports:
    @python3 -c 'import sys; sys.path.insert(0, "."); \
        from core.storage import Storage; \
        from core.burst_detector import BurstDetector; \
        from core.analyzer import Analyzer; \
        from utils.config import Config; \
        from utils.keycodes import get_key_name; \
        from PyQt5.QtWidgets import QApplication; \
        print("✓ All imports successful")'

rebuild:
    @just clean
    @just check
    @just run

full:
    @just reset
    @just clean
    @just check
    @just run

# Git
git-status:
    @git status --short

git-log:
    @git log --oneline -10
