# VS Code for the Web - Azure AI Foundry

We've generated a simple development environment for you to play with sample code to create and run the agent that you built in the Azure AI Foundry playground.

The Azure AI Foundry extension provides tools to help you build, test, and deploy AI models and AI Applications directly from VS Code. It offers simplified operations for interacting with your models, agents, and threads without leaving your development environment. Click on the Azure AI Foundry Icon on the left to see more.

Follow the instructions below to get started!

## Open the terminal

Press ``Ctrl-` `` &nbsp; to open a terminal window.

## Run your model locally

To run the model that you deployed in AI Foundry, and view the output in the terminal run the following command:

```bash
python run_model.py
```


## Add, provision and deploy web app that uses the model

To add a web app that uses your model, run:

```bash
azd init -t https://github.com/Azure-Samples/get-started-with-ai-chat
```

You can provision and deploy this web app using:

```bash
azd up
```

To delete the web app and stop incurring any charges, run:

```bash
azd down
```



## Continuing on your local desktop

You can keep working locally on VS Code Desktop by clicking "Continue On Desktop..." at the bottom left of this screen. Be sure to take the .env file with you using these steps:

- Right-click the .env file
- Select "Download"
- Move the file from your Downloads folder to the local git repo directory
- For Windows, you will need to rename the file back to .env using right-click "Rename..."

## Minimal Required Deployment (Container Apps)

Use only the steps below for a working cloud deployment of this repo.

1. Deploy the app:

```bash
RG=med-doc LOCATION=eastus ACR_NAME=lab2phracr ACA_ENV=lab2phr-env APP_NAME=lab2phr-api bash infra/deploy.sh
```

2. Sync runtime configuration from your `.env` into Container App settings:

```bash
set -euo pipefail; RG=med-doc APP=lab2phr-api ENV_FILE=.env; mapfile -t LINES < <(grep -Ev '^\s*($|#)' "$ENV_FILE" | sed 's/\r$//'); SECRET_ARGS=(); ENV_ARGS=(); for line in "${LINES[@]}"; do key="${line%%=*}"; val="${line#*=}"; key="$(echo "$key" | xargs)"; val="$(echo "$val" | sed -E 's/^[[:space:]]+|[[:space:]]+$//g')"; if [[ "$val" =~ ^\".*\"$ ]] || [[ "$val" =~ ^\'.*\'$ ]]; then val="${val:1:${#val}-2}"; fi; if [[ "$key" =~ (KEY|SECRET|TOKEN|PASSWORD) ]]; then secret_name="$(echo "$key" | tr '[:upper:]_' '[:lower:]-')"; SECRET_ARGS+=("${secret_name}=${val}"); ENV_ARGS+=("${key}=secretref:${secret_name}"); else ENV_ARGS+=("${key}=${val}"); fi; done; if [ "${#SECRET_ARGS[@]}" -gt 0 ]; then az containerapp secret set -g "$RG" -n "$APP" --secrets "${SECRET_ARGS[@]}"; fi; az containerapp update -g "$RG" -n "$APP" --set-env-vars "${ENV_ARGS[@]}"
```

3. Grant the Container App managed identity access to ACR (required for image pulls):

```bash
PID=$(az containerapp identity show -g med-doc -n lab2phr-api --query principalId -o tsv)
ACR_ID=$(az acr show -n lab2phracr --query id -o tsv)
az role assignment create --assignee-object-id "$PID" --assignee-principal-type ServicePrincipal --role AcrPull --scope "$ACR_ID"
```

4. Grant the Container App managed identity access to the Azure AI Project.
   In Azure Portal, open project `Lab2Phr` and assign role `Azure AI Developer` to managed identity `lab2phr-api`.

5. Grant the Container App managed identity access to Blob storage (required so chat tools can read files by blob URL). The storage account name is the host of `BLOB_CONTAINER_URL` in `.env` (written by `infra/bootstrap.sh`):

```bash
PID=$(az containerapp identity show -g med-doc -n lab2phr-api --query principalId -o tsv)
STORAGE_ACCOUNT=$(awk -F[/.] '/^BLOB_CONTAINER_URL=/{print $4}' .env)
STORAGE_SCOPE=$(az storage account show -g med-doc -n "$STORAGE_ACCOUNT" --query id -o tsv)
az role assignment create --assignee-object-id "$PID" --assignee-principal-type ServicePrincipal --role "Storage Blob Data Reader" --scope "$STORAGE_SCOPE"
```

6. Ensure query uses the blob-ingested index:

```bash
az containerapp update -g med-doc -n lab2phr-api --set-env-vars AZURE_SEARCH_INDEX_NAME="medical-images-blob-index"
```

7. Apply a restart revision and test endpoints:

```bash
az containerapp update -g med-doc -n lab2phr-api --set-env-vars RESTART_AT="$(date +%s)"
FQDN=$(az containerapp show -g med-doc -n lab2phr-api --query properties.configuration.ingress.fqdn -o tsv)
curl -i "https://$FQDN/healthz"
curl -i "https://$FQDN/docs"
curl -sS -X POST "https://$FQDN/agents/query" -H "Content-Type: application/json" -d '{"query":"report","k":3}'
curl -i -X POST "https://$FQDN/agents/chat" -H "Content-Type: application/json" -d '{"message":"hello"}'
```
