#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
OPUS_DIR="$REPO_DIR/third_party/opus-1.6.1"
BUILD_DIR="$OPUS_DIR/build-host-make"

if [[ ! -d "$OPUS_DIR" ]]; then
	echo "Missing $OPUS_DIR. Download official libopus first." >&2
	exit 1
fi

CMAKE_BIN="${CMAKE_BIN:-}"
if [[ -z "$CMAKE_BIN" ]]; then
	if command -v cmake >/dev/null 2>&1; then
		CMAKE_BIN="$(command -v cmake)"
	elif [[ -x /opt/nordic/ncs/toolchains/0c0f19d91c/bin/cmake ]]; then
		CMAKE_BIN=/opt/nordic/ncs/toolchains/0c0f19d91c/bin/cmake
	else
		echo "Could not find cmake." >&2
		exit 1
	fi
fi

GENERATOR="${CMAKE_GENERATOR:-Unix Makefiles}"

"$CMAKE_BIN" -S "$OPUS_DIR" -B "$BUILD_DIR" -G "$GENERATOR" \
	-DOPUS_BUILD_SHARED_LIBRARY=ON \
	-DOPUS_BUILD_PROGRAMS=OFF \
	-DOPUS_BUILD_TESTING=OFF \
	-DOPUS_INSTALL_PKG_CONFIG_MODULE=OFF \
	-DOPUS_INSTALL_CMAKE_CONFIG_MODULE=OFF

"$CMAKE_BIN" --build "$BUILD_DIR" --target opus
