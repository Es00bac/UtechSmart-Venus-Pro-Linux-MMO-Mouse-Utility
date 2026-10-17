#!/bin/bash
set -e

cd "$(dirname "$0")"
echo "Installing Venus Pro Linux utility..."

# Install the same payload the distribution packages ship. The udev rule goes
# to /etc below, since this is a local administrator install.
sudo bash -c 'source packaging/lib.sh && venus_install_payload / /usr no'

# Remove files that older versions of this script installed under other names.
sudo rm -f /usr/share/applications/venusprolinux.desktop \
    /usr/share/icons/hicolor/512x512/apps/venusprolinux.png \
    /usr/share/metainfo/com.github.es00bac.venusprolinux.appdata.xml \
    /etc/udev/rules.d/99-venus-pro.rules

# Update icon cache
sudo gtk-update-icon-cache -f /usr/share/icons/hicolor/ 2>/dev/null || true

# Install the reviewed udev rules rather than maintaining a second copy here.
sudo install -Dm644 packaging/linux/70-venus-pro.rules /etc/udev/rules.d/70-venus-pro.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hidraw
echo "udev rules installed to /etc/udev/rules.d/70-venus-pro.rules"
echo "Unplug and reconnect the mouse/receiver so the new ACL is applied."
