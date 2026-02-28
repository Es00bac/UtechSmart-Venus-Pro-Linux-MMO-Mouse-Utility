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

# Create launcher script
cat << 'LAUNCHER' | sudo tee /usr/bin/venusprolinux > /dev/null
#!/usr/bin/env python3
import os
import sys
os.execv(sys.executable, [sys.executable, "/usr/share/venusprolinux/venus_gui.py"] + sys.argv[1:])
LAUNCHER

sudo chmod 755 /usr/bin/venusprolinux

# Update icon cache
sudo gtk-update-icon-cache -f /usr/share/icons/hicolor/ 2>/dev/null || true

# Install udev rules for non-root access (hidraw for hidapi, usb for pyusb magic unlock)
cat << 'UDEV' | sudo tee /etc/udev/rules.d/99-venus-pro.rules > /dev/null
# Venus Pro (Wireless Receiver)
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="25a7", ATTRS{idProduct}=="fa07", MODE="0666"
SUBSYSTEM=="usb", ATTRS{idVendor}=="25a7", ATTRS{idProduct}=="fa07", MODE="0666"
# Venus Pro (Wired)
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="25a7", ATTRS{idProduct}=="fa08", MODE="0666"
SUBSYSTEM=="usb", ATTRS{idVendor}=="25a7", ATTRS{idProduct}=="fa08", MODE="0666"
# Venus MMO (Holtek variant)
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="04d9", ATTRS{idProduct}=="fc55", MODE="0666"
SUBSYSTEM=="usb", ATTRS{idVendor}=="04d9", ATTRS{idProduct}=="fc55", MODE="0666"
UDEV
sudo udevadm control --reload-rules && sudo udevadm trigger
echo "udev rules installed to /etc/udev/rules.d/99-venus-pro.rules"
