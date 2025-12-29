#!/usr/bin/env bash
# Installation script for RealTypeCoach

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "RealTypeCoach Installation Script"
echo "================================="
echo ""

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check if a Python package is installed
python_package_exists() {
    python3 -c "import $1" 2>/dev/null
}

# Function to print status
print_status() {
    local status=$1
    local message=$2
    if [ "$status" = "OK" ]; then
        echo -e "[${GREEN}OK${NC}] $message"
    elif [ "$status" = "FAIL" ]; then
        echo -e "[${RED}FAIL${NC}] $message"
    elif [ "$status" = "WARN" ]; then
        echo -e "[${YELLOW}WARN${NC}] $message"
    else
        echo "[$status] $message"
    fi
}

echo "Step 1: Checking system prerequisites..."
echo "---------------------------------------"

# Check if running on Linux
if [ "$(uname)" != "Linux" ]; then
    print_status "FAIL" "RealTypeCoach only supports Linux"
    exit 1
fi
print_status "OK" "Running on Linux"

# Check if python3 is available
if command_exists python3; then
    PYTHON_VERSION=$(python3 --version | awk '{print $2}')
    print_status "OK" "Python 3 found (version $PYTHON_VERSION)"
else
    print_status "FAIL" "Python 3 is required but not installed"
    exit 1
fi

# Check Python version (requires 3.10+)
PYTHON_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)')
PYTHON_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
    print_status "FAIL" "Python 3.10 or higher is required (found $PYTHON_MAJOR.$PYTHON_MINOR)"
    exit 1
fi
print_status "OK" "Python version is 3.10+"

echo ""
echo "Step 2: Checking required Python packages..."
echo "--------------------------------------------"

# Check PyQt5
if python_package_exists PyQt5; then
    print_status "OK" "PyQt5 is installed"
else
    print_status "FAIL" "PyQt5 is not installed"
    echo ""
    echo "To install PyQt5, run:"
    echo "  sudo apt install python3-pyqt5"
    echo "  sudo dnf install python3-qt5"
    echo "  sudo pacman -S python-pyqt5"
    exit 1
fi

# Check PyQt5.QtSvg
if python_package_exists PyQt5.QtSvg; then
    print_status "OK" "PyQt5.QtSvg is installed"
else
    print_status "FAIL" "PyQt5.QtSvg is not installed"
    echo ""
    echo "To install PyQt5.QtSvg, run:"
    echo "  sudo apt install python3-pyqt5.qtsvg"
    echo "  sudo dnf install python3-qt5"
    echo "  sudo pacman -S python-pyqt5"
    exit 1
fi

# Check evdev
if python_package_exists evdev; then
    print_status "OK" "evdev is installed"
else
    print_status "FAIL" "evdev is not installed"
    echo ""
    echo "To install evdev, run:"
    echo "  pip install evdev --user"
    exit 1
fi

echo ""
echo "Step 3: Creating data directory..."
echo "-----------------------------------"

INSTALL_DIR="$HOME/.local/share/realtypecoach"
mkdir -p "$INSTALL_DIR"
print_status "OK" "Data directory created: $INSTALL_DIR"

echo ""
echo "Step 4: Copying application files..."
echo "------------------------------------"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Copy Python source files
cp -r "$SCRIPT_DIR"/*.py "$INSTALL_DIR/"
cp -r "$SCRIPT_DIR"/core "$INSTALL_DIR/"
cp -r "$SCRIPT_DIR"/ui "$INSTALL_DIR/"
cp -r "$SCRIPT_DIR"/utils "$INSTALL_DIR/"
cp -r "$SCRIPT_DIR"/tests "$INSTALL_DIR/"
print_status "OK" "Application files copied to: $INSTALL_DIR"

echo ""
echo "Step 5: Generating icons..."
echo "---------------------------"

python3 -c "from utils.icon_generator import save_icon; save_icon('$INSTALL_DIR/icon.svg', active=True)"
python3 -c "from utils.icon_generator import save_icon; save_icon('$INSTALL_DIR/icon_paused.svg', active=False)"
python3 -c "from utils.icon_generator import save_icon; save_icon('$INSTALL_DIR/icon_stopping.svg', stopping=True)"
print_status "OK" "Icons generated"

echo ""
echo "Step 6: Installing to system..."
echo "-------------------------------"

BIN_DIR="$HOME/.local/bin"
APPLICATIONS_DIR="$HOME/.local/share/applications"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Create wrapper script
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/realtypecoach" << EOF
#!/usr/bin/env python3
import sys
sys.path.insert(0, '$INSTALL_DIR')
from main import main
if __name__ == '__main__':
    main()
EOF

chmod +x "$BIN_DIR/realtypecoach"
print_status "OK" "Wrapper script installed: $BIN_DIR/realtypecoach"

# Create desktop entry
mkdir -p "$APPLICATIONS_DIR"
cat > "$APPLICATIONS_DIR/realtypecoach.desktop" << EOF
[Desktop Entry]
Name=RealTypeCoach
GenericName=Typing Analysis Tool
Comment=KDE Wayland typing analysis application
Exec=$BIN_DIR/realtypecoach
Icon=$INSTALL_DIR/icon.svg
Type=Application
Categories=Utility;System;Accessibility;
Keywords=typing;keyboard;analysis;speed;wpm;
Terminal=false
StartupNotify=false
EOF
print_status "OK" "Desktop entry installed: $APPLICATIONS_DIR/realtypecoach.desktop"

# Update desktop database
update-desktop-database "$APPLICATIONS_DIR" 2>/dev/null || true
print_status "OK" "Desktop database updated"

echo ""
echo "========================================"
echo "Installation completed successfully!"
echo "========================================"
echo ""
echo "To start RealTypeCoach:"
echo "  - From application menu: Launch 'RealTypeCoach'"
echo "  - From terminal: type 'realtypecoach'"
echo "  - Or run: python3 $SCRIPT_DIR/main.py"
echo ""
echo "To uninstall:"
echo "  Run: $SCRIPT_DIR/uninstall.sh"
echo ""
