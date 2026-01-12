#!/bin/bash
set -e

cd /home/cabewse/VenusProLinux

echo "Installing Venus Pro Linux utility..."

# Install main files
sudo install -Dm755 venus_gui.py /usr/share/venusprolinux/venus_gui.py
sudo install -Dm644 venus_protocol.py /usr/share/venusprolinux/venus_protocol.py
sudo install -Dm644 staging_manager.py /usr/share/venusprolinux/staging_manager.py
sudo install -Dm644 transaction_controller.py /usr/share/venusprolinux/transaction_controller.py
sudo install -Dm644 mouseimg.png /usr/share/venusprolinux/mouseimg.png

# Install icon
sudo install -Dm644 icon.png /usr/share/icons/hicolor/512x512/apps/venusprolinux.png

# Install desktop entry
sudo install -Dm644 venusprolinux.desktop /usr/share/applications/venusprolinux.desktop

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

echo "Note: You may need to setup udev rules for non-root access:"
echo 'echo "SUBSYSTEM==\"usb\", ATTRS{idVendor}==\"25a7\", ATTRS{idProduct}==\"fa07\", MODE=\"0666\"" | sudo tee /etc/udev/rules.d/99-venus-pro.rules'
echo 'echo "SUBSYSTEM==\"usb\", ATTRS{idVendor}==\"25a7\", ATTRS{idProduct}==\"fa08\", MODE=\"0666\"" | sudo tee -a /etc/udev/rules.d/99-venus-pro.rules'
echo 'echo "SUBSYSTEM==\"usb\", ATTRS{idVendor}==\"04d9\", ATTRS{idProduct}==\"fc55\", MODE=\"0666\"" | sudo tee -a /etc/udev/rules.d/99-venus-pro.rules'
echo 'sudo udevadm control --reload-rules && sudo udevadm trigger'
