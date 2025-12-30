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

# Ask about database and related files
DATA_DIR="$INSTALL_DIR/data"
DB_PATH="$DATA_DIR/realtypecoach.db"
if [ -f "$DB_PATH" ] || ls "$DATA_DIR"/*.db.*.backup 2>/dev/null || ls "$DATA_DIR"/test*.db 2>/dev/null; then
    echo ""
    echo "Remove database files? (contains all typing history, statistics, backups, and test files)"
    read -p "Remove all database files from $DATA_DIR? [y/N]: " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Removing database files from: $DATA_DIR"
        rm -f "$DATA_DIR"/*.db "$DATA_DIR"/*.db.*.backup "$DATA_DIR"/test*.db 2>/dev/null || true
    else
        echo "Keeping database files in: $DATA_DIR"
    fi
fi

# Ask about remaining data directory
echo ""
echo "Keep remaining application data in $INSTALL_DIR? (settings, logs)"
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
