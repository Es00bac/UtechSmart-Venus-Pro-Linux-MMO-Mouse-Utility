#!/usr/bin/env bash

# Shared helpers for the distribution package builders.
set -euo pipefail

VENUS_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENUS_APP_ID="com.github.es00bac.venusprolinux"
VENUS_PACKAGE_NAME="venusprolinux"

venus_resolve_version() {
    local requested="${1:-${VERSION:-}}"

    if [[ -z "${requested}" ]]; then
        requested="$(git -C "${VENUS_REPO_ROOT}" describe --tags --exact-match 2>/dev/null || true)"
    fi
    requested="${requested#v}"

    if [[ ! "${requested}" =~ ^[0-9]+([.][0-9]+)*([~-][0-9A-Za-z.+-]+)?$ ]]; then
        echo "A release version is required (for example: 0.3.0)." >&2
        return 2
    fi

    printf '%s\n' "${requested}"
}

venus_prepare_dist() {
    VENUS_DIST_DIR="${DIST_DIR:-${VENUS_REPO_ROOT}/dist}"
    mkdir -p "${VENUS_DIST_DIR}"
}

venus_install_payload() {
    local root="$1"
    local prefix="${2:-/usr}"
    local include_udev="${3:-yes}"
    local app_dir="${root}${prefix}/share/venusprolinux"
    local applications_dir="${root}${prefix}/share/applications"
    local icons_dir="${root}${prefix}/share/icons/hicolor/1024x1024/apps"
    local metainfo_dir="${root}${prefix}/share/metainfo"
    local doc_dir="${root}${prefix}/share/doc/${VENUS_PACKAGE_NAME}"

    install -d "${app_dir}" "${applications_dir}" "${icons_dir}" \
        "${metainfo_dir}" "${doc_dir}" "${root}${prefix}/bin"

    install -m644 \
        "${VENUS_REPO_ROOT}/venus_gui.py" \
        "${VENUS_REPO_ROOT}/venus_protocol.py" \
        "${VENUS_REPO_ROOT}/holtek_protocol.py" \
        "${VENUS_REPO_ROOT}/device_driver.py" \
        "${VENUS_REPO_ROOT}/staging_manager.py" \
        "${VENUS_REPO_ROOT}/transaction_controller.py" \
        "${VENUS_REPO_ROOT}/mouseimg.png" \
        "${VENUS_REPO_ROOT}/icon.png" \
        "${app_dir}/"

    install -m755 "${VENUS_REPO_ROOT}/packaging/linux/venusprolinux" \
        "${root}${prefix}/bin/venusprolinux"
    install -m644 "${VENUS_REPO_ROOT}/packaging/linux/${VENUS_APP_ID}.desktop" \
        "${applications_dir}/${VENUS_APP_ID}.desktop"
    install -m644 "${VENUS_REPO_ROOT}/icon.png" \
        "${icons_dir}/${VENUS_APP_ID}.png"
    install -m644 "${VENUS_REPO_ROOT}/${VENUS_APP_ID}.appdata.xml" \
        "${metainfo_dir}/${VENUS_APP_ID}.metainfo.xml"

    install -m644 \
        "${VENUS_REPO_ROOT}/README.md" \
        "${VENUS_REPO_ROOT}/PROTOCOL.md" \
        "${VENUS_REPO_ROOT}/docs/MACRO_EDITOR.md" \
        "${doc_dir}/"
    install -m644 "${VENUS_REPO_ROOT}/LICENSE" "${doc_dir}/copyright"

    if [[ "${include_udev}" == "yes" ]]; then
        install -Dm644 "${VENUS_REPO_ROOT}/packaging/linux/99-venus-pro.rules" \
            "${root}/usr/lib/udev/rules.d/99-venus-pro.rules"
    fi
}
