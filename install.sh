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

# Check if user is in the 'input' group
if groups | grep -q '\binput\b'; then
    print_status "OK" "User is in the 'input' group"
else
    print_status "WARN" "User is not in the 'input' group - the application will not work without it!"
    echo ""
    echo -e "${YELLOW}To fix this, run:${NC}"
    echo "  sudo usermod -aG input \$USER"
    echo ""
    echo "Then log out and log back in for the changes to take effect."
    echo ""
fi

echo ""
echo "Step 2: Setting up virtual environment..."
echo "------------------------------------------"

# Create virtual environment if not exists
if [ -d ".venv" ]; then
    print_status "OK" "Virtual environment already exists"
else
    echo "Creating virtual environment with Python 3.14..."
    uv venv --python 3.14.2 .venv
    print_status "OK" "Virtual environment created"
fi

# Install dependencies from pyproject.toml
echo "Installing dependencies..."
uv pip install -e . --python .venv/bin/python

# Verify installation
if .venv/bin/python3 -c "import PySide6" 2>/dev/null; then
    PYSIDE6_VERSION=$(.venv/bin/python3 -c "import PySide6; print(PySide6.__version__)")
    print_status "OK" "PySide6 $PYSIDE6_VERSION installed"
fi

if .venv/bin/python3 -c "import pandas" 2>/dev/null; then
    print_status "OK" "pandas installed"
fi

echo ""
echo "Step 4: Creating data directory..."
echo "-----------------------------------"

INSTALL_DIR="$HOME/.local/share/realtypecoach"
mkdir -p "$INSTALL_DIR"
print_status "OK" "Data directory created: $INSTALL_DIR"

echo ""
echo "Step 6: Copying application files..."
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
echo "Step 7: Generating icons..."
echo "---------------------------"

.venv/bin/python3 -c "from utils.icon_generator import save_icon; save_icon('$INSTALL_DIR/icon.svg', active=True)"
.venv/bin/python3 -c "from utils.icon_generator import save_icon; save_icon('$INSTALL_DIR/icon_paused.svg', active=False)"
.venv/bin/python3 -c "from utils.icon_generator import save_icon; save_icon('$INSTALL_DIR/icon_stopping.svg', stopping=True)"
print_status "OK" "Icons generated"

echo ""
echo "Step 8: Installing to system..."
echo "-------------------------------"

BIN_DIR="$HOME/.local/bin"
APPLICATIONS_DIR="$HOME/.local/share/applications"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Create production virtual environment at install location
echo "Creating production virtual environment with Python 3.14..."
# Remove existing venv if present
if [ -d "$INSTALL_DIR/.venv" ]; then
    rm -rf "$INSTALL_DIR/.venv"
fi
uv venv --python 3.14.2 "$INSTALL_DIR/.venv"
print_status "OK" "Virtual environment created at: $INSTALL_DIR/.venv"

# Install dependencies in production venv
echo "Installing dependencies..."
uv pip install -e "$SCRIPT_DIR" --python "$INSTALL_DIR/.venv/bin/python" --quiet
print_status "OK" "Dependencies installed"

# Create wrapper script
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/realtypecoach" << 'EOF'
#!/usr/bin/env bash
INSTALL_DIR="$HOME/.local/share/realtypecoach"
if [ -d "$INSTALL_DIR/.venv/bin" ]; then
    exec "$INSTALL_DIR/.venv/bin/python3" "$INSTALL_DIR/main.py" "$@"
else
    exec python3 "$INSTALL_DIR/main.py" "$@"
fi
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
