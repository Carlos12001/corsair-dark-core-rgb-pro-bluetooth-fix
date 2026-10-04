#!/bin/sh
# Installs the service that keeps the Bluetooth adapter on the LE 1M PHY.
set -e
[ "$(id -u)" = 0 ] || { echo "Run as root: sudo ./install.sh"; exit 1; }
cd "$(dirname "$0")"
command -v btmgmt >/dev/null || { echo "btmgmt not found: install bluez-utils (Arch) / bluez (Debian, Fedora)"; exit 1; }
command -v dbus-monitor >/dev/null || { echo "dbus-monitor not found: install dbus"; exit 1; }
install -m755 bt-le-1m-phy /usr/local/bin/bt-le-1m-phy
install -m644 bt-le-1m-phy.service /etc/systemd/system/bt-le-1m-phy.service
systemctl daemon-reload
systemctl enable --now bt-le-1m-phy.service
sleep 2
echo "Selected PHYs now:"
btmgmt phy | grep "^Selected"
echo "Done. Put the mouse in pairing mode and pair it (see README)."
