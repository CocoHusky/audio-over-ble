#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LC3_SRC_DIR="${LC3_DIR:-}"

if [[ -z "$LC3_SRC_DIR" ]]; then
  echo "Set LC3_DIR to the SDK liblc3 source directory." >&2
  echo "Example: export LC3_DIR=/opt/nordic/ncs/v3.3.0/modules/lib/lc3" >&2
  exit 1
fi

if [[ ! -f "$LC3_SRC_DIR/include/lc3.h" ]]; then
  echo "LC3_DIR does not contain include/lc3.h: $LC3_SRC_DIR" >&2
  exit 1
fi

BUILD_DIR="$SCRIPT_DIR/build-lc3-host"
rm -rf "$BUILD_DIR"
cmake -S "$LC3_SRC_DIR" -B "$BUILD_DIR" -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON
cmake --build "$BUILD_DIR" --config Release
cp "$BUILD_DIR"/liblc3.* "$SCRIPT_DIR/liblc3.dylib"
echo "Built $SCRIPT_DIR/liblc3.dylib"
