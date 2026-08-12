#!/bin/bash
set -e

echo "Installing Venus Pro Linux utility..."

# Install main files
sudo install -Dm755 venus_gui.py /usr/share/venusprolinux/venus_gui.py
sudo install -Dm644 venus_protocol.py /usr/share/venusprolinux/venus_protocol.py
sudo install -Dm644 holtek_protocol.py /usr/share/venusprolinux/holtek_protocol.py
sudo install -Dm644 device_driver.py /usr/share/venusprolinux/device_driver.py
sudo install -Dm644 staging_manager.py /usr/share/venusprolinux/staging_manager.py
sudo install -Dm644 transaction_controller.py /usr/share/venusprolinux/transaction_controller.py
sudo install -Dm644 mouseimg.png /usr/share/venusprolinux/mouseimg.png

# Install icon
sudo install -Dm644 icon.png /usr/share/icons/hicolor/512x512/apps/venusprolinux.png

# Install desktop entry
sudo install -Dm644 packaging/linux/venusprolinux.desktop /usr/share/applications/venusprolinux.desktop

# Install the same launcher used by distribution packages.
sudo install -Dm755 packaging/linux/venusprolinux /usr/bin/venusprolinux

# Install metadata used by desktop software centers.
sudo install -Dm644 com.github.es00bac.venusprolinux.appdata.xml \
    /usr/share/metainfo/com.github.es00bac.venusprolinux.appdata.xml

# Update icon cache
sudo gtk-update-icon-cache -f /usr/share/icons/hicolor/ 2>/dev/null || true

# Install the reviewed udev rules rather than maintaining a second copy here.
sudo install -Dm644 packaging/linux/99-venus-pro.rules /etc/udev/rules.d/99-venus-pro.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hidraw
echo "udev rules installed to /etc/udev/rules.d/99-venus-pro.rules"
echo "Unplug and reconnect the mouse/receiver so the new ACL is applied."
