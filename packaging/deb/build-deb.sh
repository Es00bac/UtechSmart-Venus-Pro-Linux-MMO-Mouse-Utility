#!/usr/bin/env bash
# Build the Debian/Ubuntu package. The payload is architecture-independent;
# Qt and HID bindings come from each distribution's native repositories.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=../lib.sh
source "${SCRIPT_DIR}/../lib.sh"

VERSION="$(venus_resolve_version "${1:-}")"
venus_prepare_dist
BUILD_ROOT="$(mktemp -d -t venusprolinux-deb.XXXXXX)"
PKG_ROOT="${BUILD_ROOT}/${VENUS_PACKAGE_NAME}_${VERSION}_all"
trap 'rm -rf "${BUILD_ROOT}"' EXIT

venus_install_payload "${PKG_ROOT}" /usr yes
install -d "${PKG_ROOT}/DEBIAN"

cat > "${PKG_ROOT}/DEBIAN/control" <<EOF
Package: ${VENUS_PACKAGE_NAME}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: all
Depends: python3 (>= 3.10), python3-hid, python3-pyqt6
Maintainer: Es00bac <es00bac@github.com>
Homepage: https://github.com/Es00bac/UtechSmart-Venus-Pro-Linux-MMO-Mouse-Utility
Description: configuration utility for UtechSmart Venus MMO mice
 Configure supported UtechSmart Venus MMO mice on Linux. Features include
 button remapping, hardware macros, RGB lighting, DPI profiles, polling rate,
 and battery monitoring.
EOF

cat > "${PKG_ROOT}/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v udevadm >/dev/null 2>&1; then
    udevadm control --reload-rules 2>/dev/null || true
fi
exit 0
EOF
chmod 755 "${PKG_ROOT}/DEBIAN/postinst"

OUTPUT="${VENUS_DIST_DIR}/${VENUS_PACKAGE_NAME}_${VERSION}_all.deb"
dpkg-deb --root-owner-group --build "${PKG_ROOT}" "${OUTPUT}"
echo "Created ${OUTPUT}"
