#!/usr/bin/env bash
# Cleanup duplicate Azure resources created during trial deploys.
#
# Keeps canonical names and deletes similarly-prefixed duplicates in the same RG.
#
# Dry-run (default):
#   ./infra/cleanup_duplicates.sh
#
# Apply deletions:
#   APPLY=1 ./infra/cleanup_duplicates.sh
set -euo pipefail

RG="${RG:-med-doc}"
KEEP_ACR="${KEEP_ACR:-lab2phracr}"
KEEP_APP="${KEEP_APP:-lab2phr-api}"
KEEP_ENV="${KEEP_ENV:-lab2phr-env}"
APPLY="${APPLY:-0}"

if ! command -v az >/dev/null 2>&1; then
  echo "az CLI not found on PATH"
  exit 1
fi

ACT="echo [DRY-RUN]"
if [[ "$APPLY" == "1" ]]; then
  ACT=""
fi

echo "RG: $RG"
echo "Keep ACR: $KEEP_ACR"
echo "Keep App: $KEEP_APP"
echo "Keep Env: $KEEP_ENV"
if [[ "$APPLY" != "1" ]]; then
  echo "Mode: DRY-RUN (set APPLY=1 to delete)"
else
  echo "Mode: APPLY"
fi

echo
echo "==> Duplicate Container Apps"
while IFS= read -r app; do
  [[ -z "$app" ]] && continue
  if [[ "$app" != "$KEEP_APP" && "$app" == ${KEEP_APP}* ]]; then
    echo "Delete container app: $app"
    [[ -n "$ACT" ]] && $ACT az containerapp delete -g "$RG" -n "$app" --yes || az containerapp delete -g "$RG" -n "$app" --yes
  fi
done < <(az containerapp list -g "$RG" --query "[].name" -o tsv)

echo
echo "==> Duplicate ACR registries"
while IFS= read -r acr; do
  [[ -z "$acr" ]] && continue
  if [[ "$acr" != "$KEEP_ACR" && "$acr" == ${KEEP_ACR}* ]]; then
    echo "Delete ACR: $acr"
    [[ -n "$ACT" ]] && $ACT az acr delete -g "$RG" -n "$acr" --yes || az acr delete -g "$RG" -n "$acr" --yes
  fi
done < <(az acr list -g "$RG" --query "[].name" -o tsv)

echo
echo "==> Duplicate Container Apps environments"
while IFS= read -r env; do
  [[ -z "$env" ]] && continue
  if [[ "$env" != "$KEEP_ENV" && "$env" == ${KEEP_ENV}* ]]; then
    echo "Delete Container Apps env: $env"
    [[ -n "$ACT" ]] && $ACT az containerapp env delete -g "$RG" -n "$env" --yes || az containerapp env delete -g "$RG" -n "$env" --yes
  fi
done < <(az containerapp env list -g "$RG" --query "[].name" -o tsv)

echo
echo "Cleanup scan complete."
