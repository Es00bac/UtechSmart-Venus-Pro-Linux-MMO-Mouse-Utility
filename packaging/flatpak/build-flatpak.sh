#!/usr/bin/env bash
# Build a single-file Flatpak bundle with its Python dependencies included.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=../lib.sh
source "${SCRIPT_DIR}/../lib.sh"

VERSION="$(venus_resolve_version "${1:-}")"
venus_prepare_dist

if [[ "${2:-}" != "--inside-container" ]]; then
    command -v docker >/dev/null || {
        echo "Docker is required to build the Flatpak bundle." >&2
        exit 1
    }
    docker run --rm --privileged \
        -v "${VENUS_REPO_ROOT}:/src" -w /src debian:13-slim \
        bash packaging/flatpak/build-flatpak.sh "${VERSION}" --inside-container
    exit
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates flatpak flatpak-builder >/dev/null

flatpak remote-add --user --if-not-exists flathub \
    https://flathub.org/repo/flathub.flatpakrepo
flatpak install --user --noninteractive -y flathub \
    org.freedesktop.Platform//25.08 org.freedesktop.Sdk//25.08

BUILD_ROOT="$(mktemp -d -t venusprolinux-flatpak.XXXXXX)"
trap 'rm -rf "${BUILD_ROOT}"' EXIT
flatpak-builder --user --force-clean --share=network \
    --install-deps-from=flathub --repo="${BUILD_ROOT}/repo" \
    "${BUILD_ROOT}/build" \
    "${SCRIPT_DIR}/${VENUS_APP_ID}.yml"

OUTPUT="${VENUS_DIST_DIR}/VenusProLinux-${VERSION}-x86_64.flatpak"
flatpak build-bundle "${BUILD_ROOT}/repo" "${OUTPUT}" \
    "${VENUS_APP_ID}" stable
chmod 644 "${OUTPUT}"
echo "Created ${OUTPUT}"
