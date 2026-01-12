#!/bin/bash
# Build AppImage for Venus Pro Linux utility
set -e

VERSION="1.0.0"
APP_NAME="VenusProLinux"
SCRIPT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
APP_DIR="/tmp/${APP_NAME}.AppDir"

echo "Building AppImage for ${APP_NAME} v${VERSION}..."

# Download appimagetool if not present
if [ ! -f "/tmp/appimagetool" ]; then
    echo "Downloading appimagetool..."
    wget -q "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage" -O /tmp/appimagetool
    chmod +x /tmp/appimagetool
fi

# Clean and create AppDir structure
rm -rf "${APP_DIR}"
mkdir -p "${APP_DIR}/usr/bin"
mkdir -p "${APP_DIR}/usr/share/venusprolinux"
mkdir -p "${APP_DIR}/usr/share/icons/hicolor/512x512/apps"

# Copy application files
cp "${SCRIPT_DIR}/venus_gui.py" "${APP_DIR}/usr/share/venusprolinux/"
cp "${SCRIPT_DIR}/venus_protocol.py" "${APP_DIR}/usr/share/venusprolinux/"
cp "${SCRIPT_DIR}/staging_manager.py" "${APP_DIR}/usr/share/venusprolinux/"
cp "${SCRIPT_DIR}/transaction_controller.py" "${APP_DIR}/usr/share/venusprolinux/"
cp "${SCRIPT_DIR}/mouseimg.png" "${APP_DIR}/usr/share/venusprolinux/"

# Copy icon
cp "${SCRIPT_DIR}/icon.png" "${APP_DIR}/usr/share/icons/hicolor/512x512/apps/venusprolinux.png"
cp "${SCRIPT_DIR}/icon.png" "${APP_DIR}/venusprolinux.png"

# Create launcher script
cat > "${APP_DIR}/usr/bin/venusprolinux" << 'EOF'
#!/usr/bin/env python3
import os
import sys

# Add the app directory to path
app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(app_dir, "share", "venusprolinux"))

# Run the GUI
exec(open(os.path.join(app_dir, "share", "venusprolinux", "venus_gui.py")).read())
EOF
chmod 755 "${APP_DIR}/usr/bin/venusprolinux"

# Create AppRun script
cat > "${APP_DIR}/AppRun" << 'EOF'
#!/bin/bash
SELF=$(readlink -f "$0")
HERE=${SELF%/*}
export PATH="${HERE}/usr/bin:${PATH}"
export PYTHONPATH="${HERE}/usr/share/venusprolinux:${PYTHONPATH}"
exec python3 "${HERE}/usr/share/venusprolinux/venus_gui.py" "$@"
EOF
chmod 755 "${APP_DIR}/AppRun"

# Create desktop file
cat > "${APP_DIR}/venusprolinux.desktop" << EOF
[Desktop Entry]
Name=Venus Pro Config
Comment=UtechSmart Venus Pro MMO Mouse Configuration Utility
Exec=venusprolinux
Icon=venusprolinux
Terminal=false
Type=Application
Categories=Settings;HardwareSettings;
EOF

# Build AppImage
cd /tmp
ARCH=x86_64 /tmp/appimagetool "${APP_DIR}" "${APP_NAME}-${VERSION}-x86_64.AppImage"

# Move to packaging directory
mv "/tmp/${APP_NAME}-${VERSION}-x86_64.AppImage" "${SCRIPT_DIR}/packaging/appimage/"

echo "AppImage created: packaging/appimage/${APP_NAME}-${VERSION}-x86_64.AppImage"
