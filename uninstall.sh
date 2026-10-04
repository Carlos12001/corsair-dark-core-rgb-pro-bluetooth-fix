#!/bin/sh
# Removes the service. 2M PHY comes back the next time the adapter is powered on.
set -e
[ "$(id -u)" = 0 ] || { echo "Run as root: sudo ./uninstall.sh"; exit 1; }
systemctl disable --now bt-le-1m-phy.service 2>/dev/null || true
rm -f /etc/systemd/system/bt-le-1m-phy.service /usr/local/bin/bt-le-1m-phy
systemctl daemon-reload
echo "Removed. Toggle Bluetooth off/on (or reboot) to restore the default PHYs."
