#!/bin/bash
# RealTypeCoach development script - kill instances, rebuild, restart

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "RealTypeCoach Development Script"
echo "=========================================="
echo

function kill_instances() {
    echo "🛑 Stopping all RealTypeCoach instances..."
    pkill -9 -f "python3.*realtypecoach" 2>/dev/null || true
    pkill -9 -f "python3.*main.py" 2>/dev/null || true
    sleep 2

    if pgrep -f "python3.*realtypecoach" > /dev/null; then
        echo "⚠️  Some instances still running, force killing..."
        ps aux | grep -E "python3.*(realtypecoach|main.py)" | grep -v grep | awk '{print $2}' | xargs -r kill -9 2>/dev/null || true
    fi

    echo "✓ All instances stopped"
    echo
}

function clean_pycache() {
    echo "🧹 Cleaning Python cache..."
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete 2>/dev/null || true
    echo "✓ Cache cleaned"
    echo
}

function reset_db() {
    echo "🗑️  Resetting database..."
    DB_PATH="$HOME/.local/share/realtypecoach/typing_data.db"
    rm -f "$DB_PATH"
    echo "✓ Database deleted"
    echo
}

function check_syntax() {
    echo "🔍 Checking Python syntax..."
    python3 -m py_compile main.py 2>&1 | head -10
    if [ $? -eq 0 ]; then
        echo "✓ Syntax OK"
    else
        echo "✗ Syntax errors found"
        return 1
    fi
    echo
}

function run_app() {
    echo "🚀 Starting RealTypeCoach..."
    echo "Press Ctrl+C to stop"
    echo

    python3 main.py
}

function watch_logs() {
    echo "📋 Watching for errors..."
    echo "Press Ctrl+C to stop watching"
    echo

    tail -f /tmp/realtypecoach.log 2>/dev/null || python3 main.py 2>&1
}

function test_imports() {
    echo "🧪 Testing imports..."
    python3 -c "
import sys
sys.path.insert(0, '.')
from core.storage import Storage
from core.burst_detector import BurstDetector
from core.analyzer import Analyzer
from utils.config import Config
from utils.keycodes import get_key_name
from PyQt5.QtWidgets import QApplication
print('✓ All imports successful')
"
    echo
}

function status() {
    echo "📊 Status:"
    echo

    # Check running processes
    if pgrep -f "python3.*realtypecoach" > /dev/null; then
        echo "  ✓ Running: $(pgrep -f "python3.*realtypecoach" | wc -l) instance(s)"
        echo "  PIDs: $(pgrep -f "python3.*realtypecoach" | tr '\n' ' ')"
    else
        echo "  ✗ Not running"
    fi
    echo

    # Check database
    DB_PATH="$HOME/.local/share/realtypecoach/typing_data.db"
    if [ -f "$DB_PATH" ]; then
        DB_SIZE=$(du -h "$DB_PATH" | cut -f1)
        echo "  ✓ Database exists (size: $DB_SIZE)"
    else
        echo "  ✗ No database found"
    fi
    echo

    # Check dependencies
    echo "  Dependencies:"
    python3 -c "import pyatspi; print('  ✓ pyatspi')" 2>/dev/null || echo "  ✗ pyatspi missing"
    python3 -c "from PyQt5.QtWidgets import QApplication; print('  ✓ PyQt5')" 2>/dev/null || echo "  ✗ PyQt5 missing"
    echo
}

# Parse arguments
case "${1:-status}" in
    kill|stop)
        kill_instances
        ;;

    clean)
        kill_instances
        clean_pycache
        ;;

    reset)
        kill_instances
        reset_db
        ;;

    check|syntax)
        check_syntax
        ;;

    test|imports)
        test_imports
        ;;

    run|start)
        kill_instances
        run_app
        ;;

    watch|logs)
        kill_instances
        watch_logs
        ;;

    rebuild)
        kill_instances
        clean_pycache
        check_syntax
        run_app
        ;;

    full)
        kill_instances
        clean_pycache
        reset_db
        check_syntax
        run_app
        ;;

    status)
        status
        ;;

    help|--help|-h)
        echo "Usage: $0 [command]"
        echo
        echo "Commands:"
        echo "  kill        - Stop all instances"
        echo "  clean       - Kill instances and clean cache"
        echo "  reset       - Kill instances and delete database"
        echo "  check       - Check Python syntax"
        echo "  test        - Test module imports"
        echo "  run         - Kill instances and run app"
        echo "  watch       - Watch logs/error output"
        echo "  rebuild     - Kill, clean, check syntax, run"
        echo "  full        - Kill, clean, reset DB, check syntax, run"
        echo "  status      - Show running status"
        echo "  help        - Show this help"
        echo
        echo "Examples:"
        echo "  $0 run       - Start the app"
        echo "  $0 rebuild   - Clean rebuild and run"
        echo "  $0 full      - Full reset and run"
        echo
        ;;

    *)
        status
        echo
        echo "Unknown command: $1"
        echo "Use 'help' for usage information"
        exit 1
        ;;
esac
