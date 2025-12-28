# RealTypeCoach Development Commands

# Running
run:
    @pkill -9 -f "python3.*realtypecoach" 2>/dev/null || true
    python3 main.py

watch:
    @just run 2>&1 | head -50

# Instance Management
kill:
    @pkill -9 -f "python3.*realtypecoach" 2>/dev/null || true
    @echo "Killed all instances"

status:
    @if pgrep -f "python3.*realtypecoach" > /dev/null; then \
        echo "Running:"; \
        pgrep -f "python3.*realtypecoach" | tr '\n' ' '; \
    else \
        echo "Not running"; \
    fi

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
check:
    @python3 -m py_compile main.py
    @echo "Syntax check passed"

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
