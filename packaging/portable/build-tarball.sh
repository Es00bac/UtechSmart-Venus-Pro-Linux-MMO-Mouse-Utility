#!/usr/bin/env bash
# Build a generic /usr payload for distributions without a native package.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=../lib.sh
source "${SCRIPT_DIR}/../lib.sh"

VERSION="$(venus_resolve_version "${1:-}")"
venus_prepare_dist
BUILD_ROOT="$(mktemp -d -t venusprolinux-portable.XXXXXX)"
PAYLOAD="${BUILD_ROOT}/${VENUS_PACKAGE_NAME}-${VERSION}-linux-any"
trap 'rm -rf "${BUILD_ROOT}"' EXIT

venus_install_payload "${PAYLOAD}" /usr yes
install -Dm644 "${VENUS_REPO_ROOT}/packaging/portable/README.txt" \
    "${PAYLOAD}/README.txt"

OUTPUT="${VENUS_DIST_DIR}/${VENUS_PACKAGE_NAME}-${VERSION}-linux-any.tar.gz"
SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-$(git -C "${VENUS_REPO_ROOT}" log -1 --format=%ct)}"
tar --sort=name --mtime="@${SOURCE_DATE_EPOCH}" --owner=0 --group=0 \
    --numeric-owner -C "${BUILD_ROOT}" -czf "${OUTPUT}" \
    "${VENUS_PACKAGE_NAME}-${VERSION}-linux-any"
echo "Created ${OUTPUT}"
