#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$APP_DIR/../.." && pwd)"

if [[ -z "${ZEPHYR_BASE:-}" ]]; then
	for candidate in \
		/opt/nordic/ncs/*/zephyr \
		"$HOME"/ncs/*/zephyr \
		"$HOME"/ncs/zephyr \
		"$HOME"/zephyrproject/zephyr
	do
		if [[ -f "$candidate/zephyr-env.sh" ]]; then
			export ZEPHYR_BASE="$candidate"
			break
		fi
	done
fi

if [[ -z "${ZEPHYR_BASE:-}" || ! -f "$ZEPHYR_BASE/zephyr-env.sh" ]]; then
	echo "Could not find Zephyr/NCS. Open the nRF Connect SDK terminal or set ZEPHYR_BASE." >&2
	exit 1
fi

if [[ -z "${ZEPHYR_SDK_INSTALL_DIR:-}" ]]; then
	for candidate in /opt/nordic/ncs/toolchains/*/opt/zephyr-sdk; do
		if [[ -f "$candidate/cmake/Zephyr-sdkConfig.cmake" ]]; then
			export ZEPHYR_SDK_INSTALL_DIR="$candidate"
			export PATH="$(cd "$candidate/../.." && pwd)/bin:$PATH"
			break
		fi
	done
fi

if [[ -n "${ZEPHYR_SDK_INSTALL_DIR:-}" ]]; then
	export ZEPHYR_TOOLCHAIN_VARIANT=zephyr
fi

export USER_CACHE_DIR="${USER_CACHE_DIR:-$REPO_DIR/build/zephyr-cache}"
export ZEPHYR_TOOLCHAIN_CAPABILITY_CACHE_DIR="${ZEPHYR_TOOLCHAIN_CAPABILITY_CACHE_DIR:-$USER_CACHE_DIR/ToolchainCapabilityDatabase}"
export CCACHE_DIR="${CCACHE_DIR:-$REPO_DIR/build/ccache}"
mkdir -p "$ZEPHYR_TOOLCHAIN_CAPABILITY_CACHE_DIR"
mkdir -p "$CCACHE_DIR"

source "$ZEPHYR_BASE/zephyr-env.sh"

BOARD="${1:-xiao_ble/nrf52840/sense}"
west -z "$ZEPHYR_BASE" build -p always -b "$BOARD" "$APP_DIR" -- \
	-DUSER_CACHE_DIR="$USER_CACHE_DIR" \
	-DZEPHYR_TOOLCHAIN_CAPABILITY_CACHE_DIR="$ZEPHYR_TOOLCHAIN_CAPABILITY_CACHE_DIR"
