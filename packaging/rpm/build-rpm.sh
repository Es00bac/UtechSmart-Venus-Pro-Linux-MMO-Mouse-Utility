#!/usr/bin/env bash
# Build the Fedora-family RPM using Fedora's native Python dependency names.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=../lib.sh
source "${SCRIPT_DIR}/../lib.sh"

VERSION="$(venus_resolve_version "${1:-}")"
venus_prepare_dist
BUILD_ROOT="$(mktemp -d -t venusprolinux-rpm.XXXXXX)"
TOPDIR="${BUILD_ROOT}/rpmbuild"
SOURCE_DIR="${BUILD_ROOT}/${VENUS_PACKAGE_NAME}-${VERSION}"
trap 'rm -rf "${BUILD_ROOT}"' EXIT

mkdir -p "${TOPDIR}"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS} \
    "${SOURCE_DIR}/packaging/linux" "${SOURCE_DIR}/docs"
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
    "${VENUS_REPO_ROOT}/packaging/linux/70-venus-pro.rules" \
    "${SOURCE_DIR}/packaging/linux/"
install -m755 "${VENUS_REPO_ROOT}/packaging/linux/venusprolinux" \
    "${SOURCE_DIR}/packaging/linux/venusprolinux"

tar -C "${BUILD_ROOT}" -czf \
    "${TOPDIR}/SOURCES/${VENUS_PACKAGE_NAME}-${VERSION}.tar.gz" \
    "${VENUS_PACKAGE_NAME}-${VERSION}"
install -m644 "${SCRIPT_DIR}/venusprolinux.spec" "${TOPDIR}/SPECS/"

rpmbuild --define "_topdir ${TOPDIR}" --define "venus_version ${VERSION}" \
    -bb "${TOPDIR}/SPECS/venusprolinux.spec"

find "${TOPDIR}/RPMS" -type f -name '*.rpm' -exec cp -v {} "${VENUS_DIST_DIR}/" \;
