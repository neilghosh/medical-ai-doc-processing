#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

rm -rf .venv
python3.12 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

echo "Installing Azure CLI..."
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash

echo "Done. Activate with: source .venv/bin/activate"
echo "az: $(command -v az || echo NOT FOUND)"
