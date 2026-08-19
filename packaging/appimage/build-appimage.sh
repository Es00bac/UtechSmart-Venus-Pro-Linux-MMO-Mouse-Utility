#!/usr/bin/env bash
# Build a self-contained x86_64 AppImage with Python, PyQt6, and hidapi bundled.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=../lib.sh
source "${SCRIPT_DIR}/../lib.sh"

VERSION="$(venus_resolve_version "${1:-}")"
venus_prepare_dist

if [[ "${2:-}" != "--inside-container" ]]; then
    command -v docker >/dev/null || {
        echo "Docker is required to build the compatibility AppImage." >&2
        exit 1
    }
    docker run --rm \
        -v "${VENUS_REPO_ROOT}:/src" -w /src ubuntu:22.04 \
        bash packaging/appimage/build-appimage.sh "${VERSION}" --inside-container
    exit
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
    ca-certificates file libdbus-1-3 libegl1 libfontconfig1 libfreetype6 \
    libfuse2 libgl1 libglib2.0-0 libudev1 libx11-6 libxcb-cursor0 \
    libxcb-icccm4 libxcb-keysyms1 libxcb-shape0 libxcb-xinerama0 libxcb1 \
    libxkbcommon-x11-0 libxkbcommon0 \
    python3 python3-pip wget >/dev/null
python3 -m pip install --disable-pip-version-check --no-cache-dir \
    'PyInstaller==6.22.2' 'PyQt6==6.11.0' 'PyQt6-Qt6==6.11.1' \
    'PyQt6-sip==13.12.0' 'hidapi==0.15.0'

BUILD_ROOT="$(mktemp -d -t venusprolinux-appimage.XXXXXX)"
APPDIR="${BUILD_ROOT}/VenusProLinux.AppDir"
trap 'rm -rf "${BUILD_ROOT}"' EXIT

python3 -m PyInstaller --noconfirm --clean --onedir --windowed \
    --distpath "${BUILD_ROOT}/pyinstaller-dist" \
    --workpath "${BUILD_ROOT}/pyinstaller-build" \
    --specpath "${BUILD_ROOT}" \
    --name venusprolinux \
    --add-data "${VENUS_REPO_ROOT}/icon.png:." \
    --add-data "${VENUS_REPO_ROOT}/mouseimg.png:." \
    venus_gui.py

install -d "${APPDIR}/usr/lib" "${APPDIR}/usr/bin" \
    "${APPDIR}/usr/share/applications" \
    "${APPDIR}/usr/share/icons/hicolor/1024x1024/apps" \
    "${APPDIR}/usr/share/metainfo"
cp -a "${BUILD_ROOT}/pyinstaller-dist/venusprolinux" \
    "${APPDIR}/usr/lib/venusprolinux"

cat > "${APPDIR}/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "${HERE}/usr/lib/venusprolinux/venusprolinux" "$@"
EOF
chmod 755 "${APPDIR}/AppRun"
ln -s ../lib/venusprolinux/venusprolinux "${APPDIR}/usr/bin/venusprolinux"

install -m644 "packaging/linux/${VENUS_APP_ID}.desktop" \
    "${APPDIR}/${VENUS_APP_ID}.desktop"
install -m644 "packaging/linux/${VENUS_APP_ID}.desktop" \
    "${APPDIR}/usr/share/applications/${VENUS_APP_ID}.desktop"
install -m644 icon.png "${APPDIR}/${VENUS_APP_ID}.png"
install -m644 icon.png \
    "${APPDIR}/usr/share/icons/hicolor/1024x1024/apps/${VENUS_APP_ID}.png"
install -m644 "${VENUS_APP_ID}.appdata.xml" \
    "${APPDIR}/usr/share/metainfo/${VENUS_APP_ID}.metainfo.xml"
install -m644 "${VENUS_APP_ID}.appdata.xml" \
    "${APPDIR}/usr/share/metainfo/${VENUS_APP_ID}.appdata.xml"

wget -q \
    https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage \
    -O "${BUILD_ROOT}/appimagetool"
chmod 755 "${BUILD_ROOT}/appimagetool"

OUTPUT="${VENUS_DIST_DIR}/VenusProLinux-${VERSION}-x86_64.AppImage"
unset SOURCE_DATE_EPOCH
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "${BUILD_ROOT}/appimagetool" \
    "${APPDIR}" "${OUTPUT}"
chmod 755 "${OUTPUT}"
echo "Created ${OUTPUT}"
