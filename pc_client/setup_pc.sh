#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required but was not found." >&2
  exit 1
fi

python3 -m venv venv
# shellcheck disable=SC1091
source venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m py_compile ble_audio_receiver.py ble_audio_control.py play_ble_audio.py

echo ""
echo "PC client environment is ready."
echo "Run the simple player with:"
echo "  cd $SCRIPT_DIR"
echo "  source venv/bin/activate"
echo "  python play_ble_audio.py"
