#!/usr/bin/env bash
# Uninstallation script for RealTypeCoach

set -e

BIN_DIR="$HOME/.local/bin"
APPLICATIONS_DIR="$HOME/.local/share/applications"
INSTALL_DIR="$HOME/.local/share/realtypecoach"

echo "Uninstalling RealTypeCoach..."

# Remove wrapper script
if [ -f "$BIN_DIR/realtypecoach" ]; then
    echo "Removing wrapper script: $BIN_DIR/realtypecoach"
    rm -f "$BIN_DIR/realtypecoach"
fi

# Remove desktop entry
if [ -f "$APPLICATIONS_DIR/realtypecoach.desktop" ]; then
    echo "Removing desktop entry: $APPLICATIONS_DIR/realtypecoach.desktop"
    rm -f "$APPLICATIONS_DIR/realtypecoach.desktop"
fi

# Update desktop database
echo "Updating desktop database..."
update-desktop-database "$APPLICATIONS_DIR" 2>/dev/null || true

# Ask about data directory
echo ""
echo "Keep application data in $INSTALL_DIR? (statistics, database, settings)"
read -p "Remove data directory? [y/N]: " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Removing data directory: $INSTALL_DIR"
    rm -rf "$INSTALL_DIR"
else
    echo "Keeping data directory: $INSTALL_DIR"
fi

echo ""
echo "Uninstallation complete!"
