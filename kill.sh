#!/bin/bash
# Dedicated kill script to avoid pkill killing just itself

echo "🛑 Stopping RealTypeCoach..."

# Kill only the actual app, not the kill script
# Use pgrep to get PIDs and kill them directly
if pgrep -f "python3.*main.py" > /dev/null 2>&1; then
    pgrep -f "python3.*main.py" | xargs -r kill -15 2>/dev/null || true
    sleep 1
    # Force kill if still running
    if pgrep -f "python3.*main.py" > /dev/null 2>&1; then
        pgrep -f "python3.*main.py" | xargs -r kill -9 2>/dev/null || true
    fi
fi

sleep 1

# Remove PID file
rm -f ~/.local/share/realtypecoach/realtypecoach.pid

echo "  ✓ All instances stopped"
