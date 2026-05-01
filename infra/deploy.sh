#!/usr/bin/env bash
# One-shot deploy of the Lab2PHR API to Azure Container Apps.
# Requires: az CLI logged in, target subscription set.
#
# Required env vars:
#   RG                    Resource group (created if missing)
#
# Behavior:
#   - If RG already has a Container App, redeploys that app (rebuild + update).
#   - If RG has no Container App, creates required dependencies + app.
#   - If multiple apps exist, set APP_NAME explicitly.
#
# Optional env vars:
#   LOCATION              Azure region. If RG exists, defaults to RG location.
#                         If RG is new, defaults to eastus.
#   ACR_NAME              ACR name. If omitted, auto-generated and uniqueness-checked.
#   ACA_ENV               Container Apps environment name. If omitted, inferred from
#                         existing app, otherwise defaults to <rg>-env
#   APP_NAME              Container app name. If omitted, inferred from existing app
#                         when unique, otherwise defaults to <rg>-api
#
# Optional env vars (forwarded into the container as plain env):
#   ENDPOINT_URL DEPLOYMENT_NAME AZURE_OPENAI_API_KEY
#   AZURE_SEARCH_ENDPOINT AZURE_SEARCH_KEY AZURE_SEARCH_QUERY_KEY AZURE_SEARCH_INDEX_NAME
#   AZURE_AI_PROJECT_ENDPOINT AGENT_MODEL_DEPLOYMENT
#   INGEST_AGENT_ID QUERY_AGENT_ID PHR_AGENT_ID ORCHESTRATOR_AGENT_ID
#   API_KEY               If set, /agents/* require header `x-api-key: <value>`
#
# Optional env vars for managed identity role assignment:
#   BLOB_CONTAINER_URL     If set, grants "Storage Blob Data Reader" on that account
#   FOUNDRY_RG             RG of the Foundry project (defaults to RG)
set -euo pipefail

: "${RG:?set RG}"

RG_SLUG=$(echo "$RG" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9-]+/-/g; s/^-+//; s/-+$//; s/-+/-/g')
if [ -z "$RG_SLUG" ]; then
  RG_SLUG="lab2phr"
fi

if [ "$(az group exists -n "$RG")" = "true" ]; then
  LOCATION="${LOCATION:-$(az group show -n "$RG" --query location -o tsv)}"

  EXISTING_APPS=$(az containerapp list -g "$RG" --query "[].name" -o tsv 2>/dev/null || true)
  APP_COUNT=$(printf '%s\n' "$EXISTING_APPS" | grep -c . || true)

  if [ -z "${APP_NAME:-}" ]; then
    if [ "$APP_COUNT" -eq 1 ]; then
      APP_NAME="$EXISTING_APPS"
    elif [ "$APP_COUNT" -gt 1 ]; then
      echo "ERROR: multiple container apps found in RG=$RG; set APP_NAME explicitly." >&2
      printf '  %s\n' $EXISTING_APPS >&2
      exit 1
    fi
  fi
else
  LOCATION="${LOCATION:-eastus}"
fi

APP_NAME="${APP_NAME:-${RG_SLUG}-api}"
APP_NAME=$(echo "$APP_NAME" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9-]+/-/g; s/^-+//; s/-+$//; s/-+/-/g' | cut -c1-32)

APP_EXISTS="false"
if az containerapp show -g "$RG" -n "$APP_NAME" >/dev/null 2>&1; then
  APP_EXISTS="true"
fi

if [ "$APP_EXISTS" = "true" ]; then
  EXISTING_ENV_ID=$(az containerapp show -g "$RG" -n "$APP_NAME" --query properties.managedEnvironmentId -o tsv)
  EXISTING_ENV_NAME=$(basename "$EXISTING_ENV_ID")
  ACA_ENV="${ACA_ENV:-$EXISTING_ENV_NAME}"
else
  ACA_ENV="${ACA_ENV:-${RG_SLUG}-env}"
fi

ACA_ENV=$(echo "$ACA_ENV" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9-]+/-/g; s/^-+//; s/-+$//; s/-+/-/g' | cut -c1-32)

find_available_acr_name() {
  local candidate="$1"
  local available

  if az acr show -n "$candidate" >/dev/null 2>&1; then
    echo "$candidate"
    return
  fi

  available=$(az acr check-name --name "$candidate" --query nameAvailable -o tsv)
  if [ "$available" = "true" ]; then
    echo "$candidate"
    return
  fi

  for i in $(seq 1 20); do
    candidate="${candidate:0:$((50-${#i}))}$i"
    if az acr check-name --name "$candidate" --query nameAvailable -o tsv | grep -qi '^true$'; then
      echo "$candidate"
      return
    fi
  done

  echo "ERROR: unable to auto-select an available ACR name, set ACR_NAME manually" >&2
  exit 1
}

if [ -z "${ACR_NAME:-}" ]; then
  if [ "$APP_EXISTS" = "true" ]; then
    EXISTING_IMAGE=$(az containerapp show -g "$RG" -n "$APP_NAME" --query "properties.template.containers[0].image" -o tsv)
    ACR_NAME_FROM_IMAGE=$(echo "$EXISTING_IMAGE" | sed -nE 's#^([a-z0-9]+)\.azurecr\.io/.*$#\1#p')
    ACR_NAME="${ACR_NAME_FROM_IMAGE:-}"
  fi

  if [ -z "${ACR_NAME:-}" ]; then
    SUB_SUFFIX=$(az account show --query id -o tsv | tr -d '-' | cut -c1-6)
    ACR_BASE=$(echo "$RG_SLUG" | tr -d '-' | cut -c1-40)
    if [ -z "$ACR_BASE" ]; then
      ACR_BASE="lab2phr"
    fi
    ACR_NAME=$(find_available_acr_name "${ACR_BASE}${SUB_SUFFIX}")
  fi
else
  ACR_NAME=$(echo "$ACR_NAME" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+//g' | cut -c1-50)
fi

echo "==> Resolved deploy settings"
echo "    RG=$RG"
echo "    LOCATION=$LOCATION"
echo "    ACR_NAME=$ACR_NAME"
echo "    ACA_ENV=$ACA_ENV"
echo "    APP_NAME=$APP_NAME"
echo "    MODE=$([ "$APP_EXISTS" = "true" ] && echo 'rebuild-redeploy' || echo 'provision-and-deploy')"

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
if [ "$APP_EXISTS" = "true" ]; then
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
fi

# Ensure managed identity has required access.
PRINCIPAL_ID=$(az containerapp identity show -g "$RG" -n "$APP_NAME" --query principalId -o tsv)
ACR_ID=$(az acr show -n "$ACR_NAME" --query id -o tsv)

ensure_role_assignment() {
  local principal_id="$1"
  local scope="$2"
  local role_name="$3"
  local existing

  existing=$(az role assignment list \
    --assignee-object-id "$principal_id" \
    --scope "$scope" \
    --query "[?roleDefinitionName=='$role_name'] | length(@)" -o tsv)

  if [ "${existing:-0}" = "0" ]; then
    az role assignment create \
      --assignee-object-id "$principal_id" \
      --assignee-principal-type ServicePrincipal \
      --role "$role_name" \
      --scope "$scope" >/dev/null
    echo "    assigned role '$role_name' on $scope"
  else
    echo "    role '$role_name' already assigned on $scope"
  fi
}

echo "==> Managed identity role assignments"
ensure_role_assignment "$PRINCIPAL_ID" "$ACR_ID" "AcrPull"

if [ -n "${BLOB_CONTAINER_URL:-}" ]; then
  STORAGE_ACCOUNT=$(echo "$BLOB_CONTAINER_URL" | sed -E 's#^https?://([^.]+)\..*$#\1#')
  if [ -n "$STORAGE_ACCOUNT" ]; then
    STORAGE_SCOPE=$(az storage account show -n "$STORAGE_ACCOUNT" --query id -o tsv)
    ensure_role_assignment "$PRINCIPAL_ID" "$STORAGE_SCOPE" "Storage Blob Data Reader"
  fi
fi

if [ -n "${AZURE_AI_PROJECT_ENDPOINT:-}" ]; then
  FOUNDRY_ACCOUNT=$(echo "$AZURE_AI_PROJECT_ENDPOINT" | sed -nE 's#^https?://([^.]+)\.services\.ai\.azure\.com/.*$#\1#p')
  FOUNDRY_PROJECT=$(echo "$AZURE_AI_PROJECT_ENDPOINT" | sed -nE 's#^.*/api/projects/([^/?]+).*$#\1#p')
  FOUNDRY_RG="${FOUNDRY_RG:-$RG}"

  if [ -n "$FOUNDRY_ACCOUNT" ] && [ -n "$FOUNDRY_PROJECT" ]; then
    SUB_ID=$(az account show --query id -o tsv)
    PROJECT_SCOPE="/subscriptions/${SUB_ID}/resourceGroups/${FOUNDRY_RG}/providers/Microsoft.CognitiveServices/accounts/${FOUNDRY_ACCOUNT}/projects/${FOUNDRY_PROJECT}"

    if az resource show --ids "$PROJECT_SCOPE" >/dev/null 2>&1; then
      ensure_role_assignment "$PRINCIPAL_ID" "$PROJECT_SCOPE" "Azure AI Developer"
    else
      echo "    skipped Azure AI Developer assignment (project scope not found: $PROJECT_SCOPE)"
    fi
  fi
fi

FQDN=$(az containerapp show -g "$RG" -n "$APP_NAME" --query properties.configuration.ingress.fqdn -o tsv)
echo
echo "Deployed: https://${FQDN}"
echo "Swagger : https://${FQDN}/docs"
echo "Health  : https://${FQDN}/healthz"
