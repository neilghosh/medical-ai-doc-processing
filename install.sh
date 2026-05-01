#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

AZ_CLI_VENV="${HOME}/.azcli-venv"
AZ_CLI_LINK="${HOME}/.local/bin/az"

rm -rf .venv
python3.12 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

if ! command -v az >/dev/null 2>&1; then
	echo "Azure CLI not found. Installing isolated Azure CLI in ${AZ_CLI_VENV}..."
	python3 -m venv "$AZ_CLI_VENV"
	"$AZ_CLI_VENV/bin/python" -m pip install --upgrade pip
	"$AZ_CLI_VENV/bin/python" -m pip install azure-cli
	mkdir -p "${HOME}/.local/bin"
	ln -sf "$AZ_CLI_VENV/bin/az" "$AZ_CLI_LINK"
	export PATH="${HOME}/.local/bin:$PATH"
else
	echo "Azure CLI already installed: $(command -v az)"
fi

echo "Done. Activate with: source .venv/bin/activate"
echo "az: $(command -v az || echo NOT FOUND)"
