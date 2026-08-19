#!/usr/bin/env bash
# Build a stable Arch package suitable for pacman -U.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=../lib.sh
source "${SCRIPT_DIR}/../lib.sh"

VERSION="$(venus_resolve_version "${1:-}")"
venus_prepare_dist
BUILD_ROOT="$(mktemp -d -t venusprolinux-arch.XXXXXX)"
SOURCE_DIR="${BUILD_ROOT}/${VENUS_PACKAGE_NAME}-${VERSION}"
trap 'rm -rf "${BUILD_ROOT}"' EXIT

mkdir -p "${SOURCE_DIR}/packaging/linux" "${SOURCE_DIR}/docs"
install -m644 \
    "${VENUS_REPO_ROOT}/venus_gui.py" \
    "${VENUS_REPO_ROOT}/venus_protocol.py" \
    "${VENUS_REPO_ROOT}/holtek_protocol.py" \
    "${VENUS_REPO_ROOT}/device_driver.py" \
    "${VENUS_REPO_ROOT}/staging_manager.py" \
    "${VENUS_REPO_ROOT}/transaction_controller.py" \
    "${VENUS_REPO_ROOT}/mouseimg.png" \
    "${VENUS_REPO_ROOT}/icon.png" \
    "${VENUS_REPO_ROOT}/${VENUS_APP_ID}.appdata.xml" \
    "${VENUS_REPO_ROOT}/README.md" \
    "${VENUS_REPO_ROOT}/PROTOCOL.md" \
    "${VENUS_REPO_ROOT}/LICENSE" \
    "${SOURCE_DIR}/"
install -m644 "${VENUS_REPO_ROOT}/docs/MACRO_EDITOR.md" "${SOURCE_DIR}/docs/"
install -m644 "${VENUS_REPO_ROOT}/packaging/linux/${VENUS_APP_ID}.desktop" \
    "${VENUS_REPO_ROOT}/packaging/linux/99-venus-pro.rules" \
    "${SOURCE_DIR}/packaging/linux/"
install -m755 "${VENUS_REPO_ROOT}/packaging/linux/venusprolinux" \
    "${SOURCE_DIR}/packaging/linux/venusprolinux"

tar -C "${BUILD_ROOT}" -czf \
    "${BUILD_ROOT}/${VENUS_PACKAGE_NAME}-${VERSION}.tar.gz" \
    "${VENUS_PACKAGE_NAME}-${VERSION}"
SOURCE_SHA256="$(sha256sum "${BUILD_ROOT}/${VENUS_PACKAGE_NAME}-${VERSION}.tar.gz" | cut -d' ' -f1)"
sed -e "s/@VERSION@/${VERSION}/g" -e "s/@SHA256@/${SOURCE_SHA256}/g" \
    "${SCRIPT_DIR}/PKGBUILD.release" > "${BUILD_ROOT}/PKGBUILD"
install -m644 "${VENUS_REPO_ROOT}/venusprolinux.install" "${BUILD_ROOT}/"

(
    cd "${BUILD_ROOT}"
    PKGDEST="${VENUS_DIST_DIR}" makepkg --clean --cleanbuild --force --nodeps --noconfirm
)
