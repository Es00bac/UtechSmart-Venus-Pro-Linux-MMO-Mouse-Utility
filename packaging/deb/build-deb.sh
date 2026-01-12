#!/bin/bash
# Build .deb package for Venus Pro Linux utility
set -e

VERSION="1.0.0"
PKG_NAME="venusprolinux"
PKG_DIR="/tmp/${PKG_NAME}_${VERSION}_all"
SCRIPT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

echo "Building .deb package for ${PKG_NAME} v${VERSION}..."

# Clean and create package structure
rm -rf "${PKG_DIR}"
mkdir -p "${PKG_DIR}/DEBIAN"
mkdir -p "${PKG_DIR}/usr/bin"
mkdir -p "${PKG_DIR}/usr/share/venusprolinux"
mkdir -p "${PKG_DIR}/usr/share/applications"
mkdir -p "${PKG_DIR}/usr/share/icons/hicolor/512x512/apps"
mkdir -p "${PKG_DIR}/usr/share/doc/venusprolinux"

# Copy application files
cp "${SCRIPT_DIR}/venus_gui.py" "${PKG_DIR}/usr/share/venusprolinux/"
cp "${SCRIPT_DIR}/venus_protocol.py" "${PKG_DIR}/usr/share/venusprolinux/"
cp "${SCRIPT_DIR}/staging_manager.py" "${PKG_DIR}/usr/share/venusprolinux/"
cp "${SCRIPT_DIR}/transaction_controller.py" "${PKG_DIR}/usr/share/venusprolinux/"
cp "${SCRIPT_DIR}/mouseimg.png" "${PKG_DIR}/usr/share/venusprolinux/"

# Copy icon and desktop file
cp "${SCRIPT_DIR}/icon.png" "${PKG_DIR}/usr/share/icons/hicolor/512x512/apps/venusprolinux.png"
cp "${SCRIPT_DIR}/venusprolinux.desktop" "${PKG_DIR}/usr/share/applications/"

# Copy documentation
cp "${SCRIPT_DIR}/README.md" "${PKG_DIR}/usr/share/doc/venusprolinux/"
cp "${SCRIPT_DIR}/PROTOCOL.md" "${PKG_DIR}/usr/share/doc/venusprolinux/"
cp "${SCRIPT_DIR}/LICENSE" "${PKG_DIR}/usr/share/doc/venusprolinux/copyright"

# Create launcher script
cat > "${PKG_DIR}/usr/bin/venusprolinux" << 'EOF'
#!/usr/bin/env python3
import os
import sys
os.execv(sys.executable, [sys.executable, "/usr/share/venusprolinux/venus_gui.py"] + sys.argv[1:])
EOF
chmod 755 "${PKG_DIR}/usr/bin/venusprolinux"

# Create control file
cat > "${PKG_DIR}/DEBIAN/control" << EOF
Package: ${PKG_NAME}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: all
Depends: python3 (>= 3.8), python3-hidapi, python3-pyqt6
Recommends: python3-evdev
Maintainer: Es00bac <es00bac@github.com>
Homepage: https://github.com/Es00bac/UtechSmart-Venus-Pro-Linux-MMO-Mouse-Utility
Description: Linux configuration utility for UtechSmart Venus Pro MMO mouse
 A professional configuration utility for the UtechSmart Venus Pro MMO
 gaming mouse on Linux. Features button remapping, macro editor, RGB
 lighting control, DPI profiles, and polling rate adjustment.
EOF

# Create postinst script
cat > "${PKG_DIR}/DEBIAN/postinst" << 'EOF'
#!/bin/bash
gtk-update-icon-cache -f /usr/share/icons/hicolor/ 2>/dev/null || true
EOF
chmod 755 "${PKG_DIR}/DEBIAN/postinst"

# Build the package
dpkg-deb --build "${PKG_DIR}"
mv "/tmp/${PKG_NAME}_${VERSION}_all.deb" "${SCRIPT_DIR}/packaging/deb/"

echo "Package created: packaging/deb/${PKG_NAME}_${VERSION}_all.deb"
