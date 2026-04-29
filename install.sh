#!/usr/bin/env bash
# One-shot setup: create venv, install deps, verify required env vars.
set -euo pipefail

cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR=".venv"

if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtual environment in $VENV_DIR ..."
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

pip install --upgrade pip >/dev/null
pip install -r requirements.txt

# Load .env if present so the check below works.
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

REQUIRED_VARS=(
  ENDPOINT_URL
  DEPLOYMENT_NAME
  AZURE_OPENAI_API_KEY
  AZURE_SEARCH_ENDPOINT
  AZURE_SEARCH_KEY
  AZURE_SEARCH_QUERY_KEY
  AZURE_SEARCH_INDEX_NAME
  DATA_FOLDER
  LAB_IMAGE_PATH
)

missing=()
for var in "${REQUIRED_VARS[@]}"; do
  if [ -z "${!var:-}" ]; then
    missing+=("$var")
  fi
done

if [ ${#missing[@]} -gt 0 ]; then
  echo "ERROR: missing required env vars: ${missing[*]}" >&2
  echo "Add them to .env or export them, then re-run ./install.sh" >&2
  exit 1
fi

echo "Setup complete. Activate the venv with: source $VENV_DIR/bin/activate"
