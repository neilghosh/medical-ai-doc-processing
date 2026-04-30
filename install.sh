#!/usr/bin/env bash
# Minimal setup: create a Python venv and install dependencies.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-}"
VENV_DIR=".venv"

# Pick a supported Python (3.10–3.13). pydantic-core has no 3.14 wheels yet.
if [ -z "$PYTHON_BIN" ]; then
  for candidate in python3.12 python3.13 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      ver=$("$candidate" -c 'import sys;print("%d.%d"%sys.version_info[:2])')
      case "$ver" in
        3.10|3.11|3.12|3.13) PYTHON_BIN="$candidate"; break ;;
      esac
    fi
  done
fi

if [ -z "$PYTHON_BIN" ]; then
  echo "ERROR: need Python 3.10–3.13. Install python3.12 and re-run." >&2
  exit 1
fi

echo "Using $PYTHON_BIN ($("$PYTHON_BIN" -V))"

[ -d "$VENV_DIR" ] || "$PYTHON_BIN" -m venv "$VENV_DIR"

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

if ! python -m pip --version >/dev/null 2>&1; then
  python -m ensurepip --upgrade >/dev/null 2>&1 || \
    curl -sS https://bootstrap.pypa.io/get-pip.py | python
fi

python -m pip install --upgrade pip >/dev/null
python -m pip install -r requirements.txt

echo
echo "Done. Activate with: source $VENV_DIR/bin/activate"
