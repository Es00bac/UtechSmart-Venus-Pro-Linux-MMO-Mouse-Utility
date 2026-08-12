#!/bin/bash
# Build RPM package for Venus Pro Linux utility
set -e

VERSION="1.0.0"
PKG_NAME="venusprolinux"
SCRIPT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
BUILD_DIR="/tmp/rpmbuild"

echo "Building .rpm package for ${PKG_NAME} v${VERSION}..."

# Create rpmbuild directory structure
mkdir -p ${BUILD_DIR}/{BUILD,RPMS,SOURCES,SPECS,SRPMS}

# Create source tarball
TARBALL_DIR="/tmp/${PKG_NAME}-${VERSION}"
rm -rf "${TARBALL_DIR}"
mkdir -p "${TARBALL_DIR}"

cp "${SCRIPT_DIR}/venus_gui.py" "${TARBALL_DIR}/"
cp "${SCRIPT_DIR}/venus_protocol.py" "${TARBALL_DIR}/"
cp "${SCRIPT_DIR}/holtek_protocol.py" "${TARBALL_DIR}/"
cp "${SCRIPT_DIR}/device_driver.py" "${TARBALL_DIR}/"
cp "${SCRIPT_DIR}/staging_manager.py" "${TARBALL_DIR}/"
cp "${SCRIPT_DIR}/transaction_controller.py" "${TARBALL_DIR}/"
cp "${SCRIPT_DIR}/mouseimg.png" "${TARBALL_DIR}/"
cp "${SCRIPT_DIR}/icon.png" "${TARBALL_DIR}/"
cp "${SCRIPT_DIR}/packaging/linux/venusprolinux.desktop" \
    "${TARBALL_DIR}/venusprolinux.desktop"
cp "${SCRIPT_DIR}/packaging/linux/99-venus-pro.rules" "${TARBALL_DIR}/"
cp "${SCRIPT_DIR}/com.github.es00bac.venusprolinux.appdata.xml" "${TARBALL_DIR}/"
cp "${SCRIPT_DIR}/README.md" "${TARBALL_DIR}/"
cp "${SCRIPT_DIR}/PROTOCOL.md" "${TARBALL_DIR}/"
cp "${SCRIPT_DIR}/docs/MACRO_EDITOR.md" "${TARBALL_DIR}/"
cp "${SCRIPT_DIR}/LICENSE" "${TARBALL_DIR}/"

cd /tmp && tar -czf "${BUILD_DIR}/SOURCES/${PKG_NAME}-${VERSION}.tar.gz" "${PKG_NAME}-${VERSION}"

# Copy spec file
cp "${SCRIPT_DIR}/packaging/rpm/venusprolinux.spec" "${BUILD_DIR}/SPECS/"

# Build the RPM
rpmbuild --define "_topdir ${BUILD_DIR}" -bb "${BUILD_DIR}/SPECS/venusprolinux.spec"

# Copy the result
cp ${BUILD_DIR}/RPMS/noarch/*.rpm "${SCRIPT_DIR}/packaging/rpm/"

echo "Package created in packaging/rpm/"
