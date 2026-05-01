#!/usr/bin/env bash
# Discover Azure resources in an existing RG (Foundry/AI Services account +
# AI Search) and write their endpoints/keys to .env (and optionally push to
# GitHub Codespaces secrets).
#
# Prereqs (run once, manually):
#   - az login && az account set --subscription <sub>
#   - gh auth login   (only if PUSH_CODESPACES=1; needs codespace:secrets scope)
#   - In the Portal create, in the same RG:
#       * Azure AI Foundry resource + project (kind=AIServices)
#         with a chat/vision model deployment (e.g. gpt-4o)
#       * Azure AI Search service
#
# Required:
#   RG                      Resource group containing both resources above
#
# Optional overrides (only needed if the RG has more than one of a kind):
#   FOUNDRY_ACCOUNT         AI Services account name
#   FOUNDRY_PROJECT         Foundry project name under that account
#   SEARCH_SERVICE          Search service name
#   OPENAI_DEPLOYMENT       Model deployment name (else first one is used)
#   SEARCH_INDEX_NAME       Defaults to "medical-images-index"
#   AGENT_MODEL_DEPLOYMENT  Defaults to OPENAI_DEPLOYMENT
#   STORAGE_ACCOUNT         Storage account name (else picked from RG if unique)
#   BLOB_CONTAINER          Blob container name (else picked from account if unique)
#   PUSH_CODESPACES=1       Also push values via `gh secret set --app codespaces`
#   GH_REPO=owner/repo      Required if PUSH_CODESPACES=1
set -euo pipefail
cd "$(dirname "$0")/.."

: "${RG:?set RG}"

# pick_one <label> <override-value> <list-cmd...>
# Runs the list command, then either echoes the override, the unique result,
# or fails with a clear message listing the candidates.
pick_one() {
  local label="$1" val="$2"; shift 2
  if [ -n "$val" ]; then echo "$val"; return; fi
  local items count
  items=$("$@")
  count=$(printf '%s\n' "$items" | grep -c . || true)
  if [ "$count" -eq 0 ]; then
    echo "ERROR: no $label found in RG=$RG" >&2; exit 1
  fi
  if [ "$count" -gt 1 ]; then
    echo "ERROR: multiple ${label}s found in RG=$RG, set the override env var:" >&2
    printf '  %s\n' $items >&2; exit 1
  fi
  echo "$items"
}

echo "==> Discovering AI Services (Foundry) account"
FOUNDRY_ACCOUNT=$(pick_one "AIServices account" "${FOUNDRY_ACCOUNT:-}" \
  az cognitiveservices account list -g "$RG" \
    --query "[?kind=='AIServices'].name" -o tsv)
echo "    account: $FOUNDRY_ACCOUNT"

ENDPOINT_URL=$(az cognitiveservices account show \
  -g "$RG" -n "$FOUNDRY_ACCOUNT" --query properties.endpoint -o tsv)
AZURE_OPENAI_API_KEY=$(az cognitiveservices account keys list \
  -g "$RG" -n "$FOUNDRY_ACCOUNT" --query key1 -o tsv)

echo "==> Discovering model deployment"
OPENAI_DEPLOYMENT=$(pick_one "deployment" "${OPENAI_DEPLOYMENT:-}" \
  az cognitiveservices account deployment list \
    -g "$RG" -n "$FOUNDRY_ACCOUNT" --query "[].name" -o tsv)
echo "    deployment: $OPENAI_DEPLOYMENT"

echo "==> Discovering Foundry project"
SUB=$(az account show --query id -o tsv)
PROJECTS_JSON=$(az rest --method get \
  --url "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.CognitiveServices/accounts/$FOUNDRY_ACCOUNT/projects?api-version=2025-04-01-preview" \
  -o json 2>/dev/null || echo '{"value":[]}')
PROJECT_NAMES=$(echo "$PROJECTS_JSON" | python3 -c 'import json,sys;print("\n".join(p["name"] for p in json.load(sys.stdin).get("value",[])))')
FOUNDRY_PROJECT=$(pick_one "Foundry project" "${FOUNDRY_PROJECT:-}" echo "$PROJECT_NAMES")
FOUNDRY_PROJECT="${FOUNDRY_PROJECT##*/}"   # strip any "account/" prefix
echo "    project: $FOUNDRY_PROJECT"

# Foundry project endpoint must use the `services.ai.azure.com` host, not the
# account's `cognitiveservices.azure.com` endpoint.
FOUNDRY_PROJECT_ENDPOINT="https://$(echo "$FOUNDRY_ACCOUNT" | tr '[:upper:]' '[:lower:]').services.ai.azure.com/api/projects/${FOUNDRY_PROJECT}"

echo "==> Discovering AI Search service"
SEARCH_SERVICE=$(pick_one "Search service" "${SEARCH_SERVICE:-}" \
  az search service list -g "$RG" --query "[].name" -o tsv)
echo "    search: $SEARCH_SERVICE"

AZURE_SEARCH_ENDPOINT="https://${SEARCH_SERVICE}.search.windows.net"
AZURE_SEARCH_KEY=$(az search admin-key show \
  -g "$RG" --service-name "$SEARCH_SERVICE" --query primaryKey -o tsv)
AZURE_SEARCH_QUERY_KEY=$(az search query-key list \
  -g "$RG" --service-name "$SEARCH_SERVICE" --query "[0].key" -o tsv)

SEARCH_INDEX_NAME="${SEARCH_INDEX_NAME:-medical-images-index}"
AGENT_MODEL_DEPLOYMENT="${AGENT_MODEL_DEPLOYMENT:-$OPENAI_DEPLOYMENT}"

echo "==> Discovering Storage account"
STORAGE_ACCOUNT=$(pick_one "Storage account" "${STORAGE_ACCOUNT:-}" \
  az storage account list -g "$RG" --query "[].name" -o tsv)
echo "    storage: $STORAGE_ACCOUNT"

BLOB_CONTAINER="${BLOB_CONTAINER:-data}"
echo "    container: $BLOB_CONTAINER"

BLOB_CONTAINER_URL="https://${STORAGE_ACCOUNT}.blob.core.windows.net/${BLOB_CONTAINER}"

echo "==> Writing .env"
cat > .env <<EOF
ENDPOINT_URL=$ENDPOINT_URL
DEPLOYMENT_NAME=$OPENAI_DEPLOYMENT
AZURE_OPENAI_API_KEY=$AZURE_OPENAI_API_KEY
AZURE_SEARCH_ENDPOINT=$AZURE_SEARCH_ENDPOINT
AZURE_SEARCH_KEY=$AZURE_SEARCH_KEY
AZURE_SEARCH_QUERY_KEY=$AZURE_SEARCH_QUERY_KEY
AZURE_SEARCH_INDEX_NAME=$SEARCH_INDEX_NAME
AZURE_AI_PROJECT_ENDPOINT=$FOUNDRY_PROJECT_ENDPOINT
AGENT_MODEL_DEPLOYMENT=$AGENT_MODEL_DEPLOYMENT
BLOB_CONTAINER_URL=$BLOB_CONTAINER_URL
EOF
echo "    wrote $(pwd)/.env"

if [ "${PUSH_CODESPACES:-0}" = "1" ]; then
  : "${GH_REPO:?set GH_REPO=owner/repo to push Codespaces secrets}"
  echo "==> Pushing Codespaces secrets to $GH_REPO"
  while IFS='=' read -r k v; do
    [ -z "$k" ] && continue
    printf '%s' "$v" | gh secret set "$k" --app codespaces --repo "$GH_REPO" --body -
    echo "    set $k"
  done < .env
fi

echo
echo "Done. Values are in .env (and Codespaces secrets if PUSH_CODESPACES=1)."
