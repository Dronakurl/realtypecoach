# Enable Accessibility on KDE (Wayland)

echo "=========================================="
echo "Enable KDE Accessibility Services"
echo "=========================================="
echo

echo "Checking AT-SPI D-Bus..."
if systemctl --user is-active at-spi-dbus-bus.service; then
    echo "✓ AT-SPI D-Bus service is RUNNING"
else
    echo "✗ AT-SPI D-Bus service is NOT running"
    echo ""
    echo "Starting AT-SPI D-Bus service..."
    systemctl --user start at-spi-dbus-bus.service
    echo "✓ AT-SPI D-Bus service started"
fi

echo
echo "Starting AT-SPI registry daemon..."
systemctl --user start at-spi-dbus-bus-launcher.service
echo "✓ AT-SPI registry started"

echo
echo "=========================================="
echo "Accessibility services should now be running."
echo "=========================================="
echo

echo "Next steps:"
echo "1. Check if AT-SPI is receiving events:"
echo "   python3 test_atspi.py"
echo
echo "2. If test shows no events, try:"
echo "   - System Settings → Accessibility → Enable assistive technologies"
echo "   - Restart RealTypeCoach: just kill && just run"
echo
   - Or reboot your system"
