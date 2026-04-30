#!/usr/bin/env bash
set -euo pipefail

RG="${RG:-med-doc}"
LOCATION="${LOCATION:-eastus}"
ACR_NAME="${ACR_NAME:-lab2phracr}"
ACA_ENV="${ACA_ENV:-lab2phr-env}"
APP_NAME="${APP_NAME:-lab2phr-api}"
IMAGE_TAG="${IMAGE_TAG:-$(date +%Y%m%d%H%M%S)}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${ACR_NAME}.azurecr.io/lab2phr-api:${IMAGE_TAG}"

ENV_PAIRS=()
for v in ENDPOINT_URL DEPLOYMENT_NAME AZURE_OPENAI_API_KEY AZURE_SEARCH_ENDPOINT AZURE_SEARCH_KEY AZURE_SEARCH_QUERY_KEY AZURE_SEARCH_INDEX_NAME BLOB_CONTAINER_URL BLOB_SAS_TOKEN AZURE_AI_PROJECT_ENDPOINT AGENT_MODEL_DEPLOYMENT ORCHESTRATOR_AGENT_ID API_KEY; do
  [ -n "${!v:-}" ] && ENV_PAIRS+=("$v=${!v}")
done

echo "[1/6] RG"
az group create -n "$RG" -l "$LOCATION" >/dev/null

echo "[2/6] ACR"
az acr show -n "$ACR_NAME" >/dev/null 2>&1 || az acr create -g "$RG" -n "$ACR_NAME" --sku Basic --admin-enabled false >/dev/null

echo "[3/6] Build"
az acr build -r "$ACR_NAME" -t "lab2phr-api:${IMAGE_TAG}" "$ROOT_DIR"

echo "[4/6] ACA Env"
az containerapp env show -g "$RG" -n "$ACA_ENV" >/dev/null 2>&1 || az containerapp env create -g "$RG" -n "$ACA_ENV" -l "$LOCATION" >/dev/null

echo "[5/6] App"
if az containerapp show -g "$RG" -n "$APP_NAME" >/dev/null 2>&1; then
  U=(az containerapp update -g "$RG" -n "$APP_NAME" --image "$IMAGE")
  [ "${#ENV_PAIRS[@]}" -gt 0 ] && U+=(--set-env-vars "${ENV_PAIRS[@]}")
  "${U[@]}" >/dev/null
else
  C=(az containerapp create -g "$RG" -n "$APP_NAME" --environment "$ACA_ENV" --image "$IMAGE" --registry-server "${ACR_NAME}.azurecr.io" --system-assigned --ingress external --target-port 8000 --min-replicas 1 --max-replicas 3)
  if az containerapp create -h 2>/dev/null | grep -q -- "--registry-identity"; then
    C+=(--registry-identity system)
  else
    # Older containerapp extension: create with a public image first, then switch to MI+ACR.
    C=(az containerapp create -g "$RG" -n "$APP_NAME" --environment "$ACA_ENV" --image "mcr.microsoft.com/k8se/quickstart:latest" --system-assigned --ingress external --target-port 8000 --min-replicas 1 --max-replicas 3)
  fi
  [ "${#ENV_PAIRS[@]}" -gt 0 ] && C+=(--env-vars "${ENV_PAIRS[@]}")
  "${C[@]}" >/dev/null
fi

# Enforce MI pull permissions and registry binding after create/update.
az containerapp identity assign -g "$RG" -n "$APP_NAME" --system-assigned >/dev/null
PID=""
for _ in $(seq 1 12); do
  PID=$(az containerapp identity show -g "$RG" -n "$APP_NAME" --query principalId -o tsv 2>/dev/null || true)
  [ -n "$PID" ] && break
  sleep 5
done
[ -n "$PID" ] || { echo "Failed to resolve system-assigned identity principalId." >&2; exit 1; }

ACR_ID=$(az acr show -n "$ACR_NAME" --query id -o tsv)
az role assignment create --assignee "$PID" --role AcrPull --scope "$ACR_ID" >/dev/null 2>&1 || true
az containerapp registry set -g "$RG" -n "$APP_NAME" --server "${ACR_NAME}.azurecr.io" --identity system >/dev/null

# Ensure the app runs the intended ACR image after MI registry binding.
U=(az containerapp update -g "$RG" -n "$APP_NAME" --image "$IMAGE")
[ "${#ENV_PAIRS[@]}" -gt 0 ] && U+=(--set-env-vars "${ENV_PAIRS[@]}")
"${U[@]}" >/dev/null

echo "[6/6] URL"
FQDN=$(az containerapp show -g "$RG" -n "$APP_NAME" --query properties.configuration.ingress.fqdn -o tsv)
echo "Deployed: https://${FQDN}"
echo "Swagger : https://${FQDN}/docs"
echo "Health  : https://${FQDN}/healthz"
