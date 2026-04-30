# Lab2PHR Demo Runbook

This is a simple, stage-friendly runbook from a fresh VS Code launch to a full agentic architecture story.

## 1. Launch and Setup (1 minute)

1. Open the project in VS Code and open a terminal in the project root.
2. Ensure `.env` exists with these keys (no fallback defaults in scripts):
   - `ENDPOINT_URL`, `DEPLOYMENT_NAME`, `AZURE_OPENAI_API_KEY`
   - `AZURE_SEARCH_ENDPOINT`, `AZURE_SEARCH_KEY`, `AZURE_SEARCH_QUERY_KEY`, `AZURE_SEARCH_INDEX_NAME`
   - `DATA_FOLDER`, `LAB_IMAGE_PATH`
3. Run the one-shot bootstrap (creates venv, installs deps, validates env):

```bash
./install.sh
source .venv/bin/activate
```

   Optional: Command Palette → "Python: Select Interpreter" → choose `.venv/bin/python` so VS Code uses the same env.

## 2. Generic Model Call Baseline (Step 0)

Goal: prove the model call works before vision/document logic.

Run:

```bash
python run_model.py
```

Talk track:
- "This confirms Azure model deployment connectivity and auth are correct."

## 3. Zero-Shot Vision Extraction (Step 1)

Goal: prove GPT-4o can read a messy report image directly.

Run:

```bash
python lab_report.py
```

Talk track:
- "No OCR pipeline code here. GPT-4o reads the image and answers directly."

## 4. Index All Reports into Vector Search (Step 2)

Goal: create searchable multimodal index entries from local report images.

Run:

```bash
python ingest_reports.py
```

Talk track:
- "We ingest vectors once, then reuse retrieval cheaply before extraction calls."

## 5. Retrieve by Clinical Intent (Step 3)

Goal: find the right report with vector search before extraction.

Run:

```bash
python query_index.py
```

Talk track:
- "This query is vector-based, so it can find relevant charts even when filenames do not contain exact keywords."

## 6. Architecture Story for Q&A

Use this model split:

1. GPT-4o for reasoning + schema extraction.
2. Azure AI Vision vectorization for multimodal embeddings.
3. Azure AI Search for cost-efficient retrieval.

Use this service tradeoff:

1. Azure AI Document Intelligence for high-volume standardized extraction pipelines.
2. GPT-4o workflows when adaptive reasoning and agent decisions are needed.

## 7. Productized Demo Track (Second Version)

Keep a separate branch/folder for the "pre-hosted" cloud demo:

1. Blob upload -> Event Grid -> Azure Function trigger.
2. Function does retrieval + extraction.
3. Store final structured record in Cosmos DB or SQL.

Suggested split:
- `main` branch: local stage demo scripts (fast and transparent).
- `prod-demo` branch: serverless hosted architecture (upload and watch it flow).

## 8. Stage Safety Checklist

1. Run `python run_model.py` once before session starts.
2. Keep 3-4 known images in `data/` with one backup image.
3. Verify index exists and query key works.
4. Keep one fallback command visible in notes for each step.
5. Rotate keys after the event.

## 9. Agentic Version (Foundry agent + FastAPI)

A single OrchestratorAgent owns all four tools. The same agent definition runs
locally and in Foundry — the SDK's `runs.create_and_process` automatically
executes the FunctionTools in the caller's process.

- `scripts.ingest_reports.ingest(path)` → tool
- `scripts.query_index.search(query, k)` → tool
- `scripts.phr_extractor.extract(image)` / `.explain(record)` → tools

Demo flow:

```bash
# Step 0/1 baselines
python -m scripts.run_model
python -m scripts.lab_report

# Capability scripts (also runnable standalone)
python -m scripts.ingest_reports
python -m scripts.query_index
python -m scripts.phr_extractor

# 1. Same scripts, run as a sequential pipeline
python -m agents.pipeline --image data/report1.jpg --query "platelet count"

# 2. Create the OrchestratorAgent in Foundry
#    Requires AZURE_AI_PROJECT_ENDPOINT in .env and `az login`.
python -m agents.bootstrap_agents
# copy the printed ORCHESTRATOR_AGENT_ID into .env

# 3. Chat with the orchestrator (it picks the right tool per turn)
python -m agents.chat

# 4. HTTP surface (Swagger at /docs)
uvicorn api.main:app --reload --port 8000

# 5. Public URL on Azure Container Apps
RG=lab2phr-rg LOCATION=eastus2 ACR_NAME=lab2phracr$RANDOM \
ACA_ENV=lab2phr-env APP_NAME=lab2phr-api \
./infra/deploy.sh
# -> https://<app>.<region>.azurecontainerapps.io/docs
```

### Housekeeping (optional, one-time)

After the move, the original top-level files are now thin re-export shims that
just forward to `scripts.*`. Delete them when convenient:

```bash
rm ingest_reports.py query_index.py phr_extractor.py lab_report.py run_model.py
rm agents/core/vision.py agents/core/phr_schema.py
chmod +x infra/deploy.sh
```

