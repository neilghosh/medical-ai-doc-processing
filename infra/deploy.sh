#!/usr/bin/env bash
# One-shot deploy of the Lab2PHR API to Azure Container Apps.
# Requires: az CLI logged in, target subscription set.
#
# Required env vars:
#   RG                    Resource group (created if missing)
#   LOCATION              Azure region (e.g. eastus2)
#   ACR_NAME              Globally unique ACR name (created if missing)
#   ACA_ENV               Container Apps environment name (created if missing)
#   APP_NAME              Container app name (created if missing)
#
# Optional env vars (forwarded into the container as plain env):
#   ENDPOINT_URL DEPLOYMENT_NAME AZURE_OPENAI_API_KEY
#   AZURE_SEARCH_ENDPOINT AZURE_SEARCH_KEY AZURE_SEARCH_QUERY_KEY AZURE_SEARCH_INDEX_NAME
#   AZURE_AI_PROJECT_ENDPOINT AGENT_MODEL_DEPLOYMENT
#   INGEST_AGENT_ID QUERY_AGENT_ID PHR_AGENT_ID ORCHESTRATOR_AGENT_ID
#   API_KEY               If set, /agents/* require header `x-api-key: <value>`
set -euo pipefail

: "${RG:?set RG}"
: "${LOCATION:?set LOCATION}"
: "${ACR_NAME:?set ACR_NAME}"
: "${ACA_ENV:?set ACA_ENV}"
: "${APP_NAME:?set APP_NAME}"

IMAGE="${ACR_NAME}.azurecr.io/lab2phr-api:latest"

echo "==> Resource group"
az group create -n "$RG" -l "$LOCATION" >/dev/null

echo "==> ACR"
az acr show -n "$ACR_NAME" >/dev/null 2>&1 || \
  az acr create -g "$RG" -n "$ACR_NAME" --sku Basic --admin-enabled false >/dev/null

echo "==> Build image in ACR"
az acr build -r "$ACR_NAME" -t "lab2phr-api:latest" .

echo "==> Container Apps environment"
az containerapp env show -g "$RG" -n "$ACA_ENV" >/dev/null 2>&1 || \
  az containerapp env create -g "$RG" -n "$ACA_ENV" -l "$LOCATION" >/dev/null

ENV_PAIRS=()
for var in ENDPOINT_URL DEPLOYMENT_NAME AZURE_OPENAI_API_KEY \
           AZURE_SEARCH_ENDPOINT AZURE_SEARCH_KEY AZURE_SEARCH_QUERY_KEY AZURE_SEARCH_INDEX_NAME \
           AZURE_AI_PROJECT_ENDPOINT AGENT_MODEL_DEPLOYMENT \
           ORCHESTRATOR_AGENT_ID API_KEY; do
  val="${!var:-}"
  [ -n "$val" ] && ENV_PAIRS+=("$var=$val")
done

echo "==> Container app"
if az containerapp show -g "$RG" -n "$APP_NAME" >/dev/null 2>&1; then
  az containerapp update -g "$RG" -n "$APP_NAME" --image "$IMAGE" \
    ${ENV_PAIRS[@]:+--set-env-vars "${ENV_PAIRS[@]}"} >/dev/null
else
  az containerapp create -g "$RG" -n "$APP_NAME" \
    --environment "$ACA_ENV" \
    --image "$IMAGE" \
    --registry-server "${ACR_NAME}.azurecr.io" \
    --system-assigned \
    --ingress external --target-port 8000 \
    --min-replicas 1 --max-replicas 3 \
    ${ENV_PAIRS[@]:+--env-vars "${ENV_PAIRS[@]}"} >/dev/null

  # Grant the system-assigned identity pull access to the registry.
  PRINCIPAL_ID=$(az containerapp identity show -g "$RG" -n "$APP_NAME" --query principalId -o tsv)
  ACR_ID=$(az acr show -n "$ACR_NAME" --query id -o tsv)
  az role assignment create --assignee "$PRINCIPAL_ID" --role AcrPull --scope "$ACR_ID" >/dev/null
fi

FQDN=$(az containerapp show -g "$RG" -n "$APP_NAME" --query properties.configuration.ingress.fqdn -o tsv)
echo
echo "Deployed: https://${FQDN}"
echo "Swagger : https://${FQDN}/docs"
echo "Health  : https://${FQDN}/healthz"
