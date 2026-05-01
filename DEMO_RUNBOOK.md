# Lab2PHR Demo Runbook

A simple, stage-friendly walkthrough from a fresh VS Code launch to the full
agentic + API story. Copy/paste commands; speaker notes for each step.

---

## 1. Setup (1 minute)

1. Open the repo in VS Code, terminal in the project root.
2. `.env` must contain (no fallback defaults):
   - `ENDPOINT_URL`, `DEPLOYMENT_NAME`, `AZURE_OPENAI_API_KEY`
   - `AZURE_SEARCH_ENDPOINT`, `AZURE_SEARCH_KEY`, `AZURE_SEARCH_QUERY_KEY`, `AZURE_SEARCH_INDEX_NAME`
   - `DATA_FOLDER`, `LAB_IMAGE_PATH`
   - `AZURE_AI_PROJECT_ENDPOINT` (only needed for sections 7+)
3. Bootstrap venv + deps:

   ```bash
   ./install.sh
   source .venv/bin/activate
   ```

   Optional: Command Palette → *Python: Select Interpreter* → `.venv/bin/python`.

4. Azure CLI for AAD-based access to Foundry:

   ```bash
   az --version || curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
   az login
   ```

---

## 2. Step 0 — Generic Model Call

Goal: prove model deployment + auth work before any vision/document logic.

```bash
python -m scripts.run_model
```

> "This single call confirms the Azure OpenAI deployment, key, and endpoint
> are wired correctly. Everything after is just adding capabilities on top."

---

## 3. Step 1 — Zero-Shot Vision Extraction

Goal: GPT-4o reads a messy lab-report image directly.

```bash
python -m scripts.lab_report
```

> "No OCR, no template — the multimodal model reads the image and answers.
> Great for prototyping; not the cheapest option for high volume."

---

## 4. Step 2 — Index All Reports into Vector Search

Goal: build a multimodal search index from local report images.

```bash
python -m scripts.ingest_reports
```

> "Embed every image once with Azure AI Vision and push to Azure AI Search.
> Retrieval is then cheap; the expensive GPT-4o call only runs on the matched
> report."

---

## 5. Step 3 — Retrieve by Clinical Intent

Goal: vector search returns the right report even with fuzzy queries.

```bash
python -m scripts.query_index
```

> "Vector search finds semantically similar reports — close layouts and
> clinical context — even when filenames have nothing to do with the query."

### 5.1 Portal-ready query JSON (optional)

```bash
python -m scripts.vectorize_image sampledata/report1.jpg > /tmp/q.json
cat /tmp/q.json
```

Paste into Azure portal → AI Search → your index → *Search explorer (JSON view)*.

Expected shape:

```json
{
  "select": "id, file_path",
  "vectorQueries": [
    { "kind": "vector", "vector": [ ... ], "fields": "image_vector", "k": 5 }
  ]
}
```

### Speaker notes — why "similar" reports score close

- Pure vector search (`search_text=None`, `image_vector` k-NN) always returns
  nearest neighbours — no exact-match guarantee.
- `@search.score` is similarity, not relevance to a keyword.
- For exact terms like `HBA1C`, add OCR text to the index and run **hybrid**
  search (text + vector) with a score threshold.

---

## 6. Step 4 — Sequential Pipeline (no agent yet)

Goal: chain `search → extract → explain` in plain Python.

```bash
python -m agents.pipeline --image sampledata/report1.jpg --query "platelet count"
```

> "Same capability functions, just composed by code. This is the baseline the
> agent will replace."

---

## 7. Step 5 — ClinicAssistant Agent (Foundry)

A single agent, `clinic-assistant`, owns all four tools. The SDK's
`runs.create_and_process` runs the `requires_action / submit_tool_outputs`
loop for us; the FunctionTools execute in this Python process.

Tools the agent can call:

- `scripts.ingest_reports.ingest(path)`
- `scripts.query_index.search(query, k)`
- `scripts.phr_extractor.extract(image_path)`
- `scripts.phr_extractor.explain(record)`

### 7.1 One-shot CLI

```bash
# fresh thread each call
python -m agents.clinic_assitant "explain sampledata/report1.jpg"

# continue an existing thread (id printed by the previous run)
python -m agents.clinic_assitant --thread thread_xxx "what's the platelet value?"
```

### 7.2 Interactive REPL (one shared thread, retains context)

```bash
python -m agents.chat
# you> ingest sampledata/report1.jpg
# you> what's the platelet value?
# you> exit
```

### 7.3 See it in Foundry

ai.azure.com → your project → **Agents** (the `clinic-assistant` definition)
and **Threads** (full message + tool-call trace per `thread_id`).

> "The same Python tool functions are now invoked by the model — the agent
> picks the tool; we don't write routing code. Threads give us
> per-conversation memory; the agent itself is reusable across users."

---

## 7b. Step 5b — Multi-Agent Workflow (agent-to-agent handoff)

Goal: show *agents talking to agents* — the output of one agent is the input
to the next, no human in between. Built with the **Microsoft Agent Framework**
`WorkflowBuilder` + `@executor` decorators.

Two specialists wired into a graph:

- **`query_agent`** — tool `search`. Picks the best-matching report and
  returns the file path.
- **`summarizer_agent`** — tools `extract` + `explain`. Reads that report
  and answers the user's question.

```bash
python -m agents.workflow "Summarise the CBC report"
```

Expected console flow (the `>>` / `<<` lines are the A2A handoff):

```
[tracing] -> Azure App Insights (Foundry Tracing tab)
[workflow] query -> summarize    input='Summarise the CBC report'

>> query_agent      <- 'Summarise the CBC report'
<< query_agent      -> /workspaces/.../sampledata/report1.jpg

>> summarizer_agent <- /workspaces/.../sampledata/report1.jpg
<< summarizer_agent -> Here is a friendly summary of your CBC report ...

[final output] ...
[Foundry agents]  query_agent=asst_...  summarizer_agent=asst_...
```

> "Notice nobody re-prompted. `query_agent`'s reply (a file path) became the
> input to `summarizer_agent` automatically — that's the agent-to-agent edge
> defined in `WorkflowBuilder`."

### 7b.1 See it in Foundry

- **Agents** tab → both `query_agent` and `summarizer_agent` show up as
  separate agent definitions, each with their own threads + run-step trace.
- **Tracing** tab (requires `APPLICATIONINSIGHTS_CONNECTION_STRING` in `.env`,
  written automatically by `infra/bootstrap.sh`) → one trace per workflow run
  with nested spans:
  `workflow.run → executor.process query → Invoke Agent query_agent →
  executor.process summarize → Invoke Agent summarizer_agent`.
  Click any LLM span to see the raw prompt / completion (sensitive-data mode
  is on for the demo).

> "The Agents tab shows *what* each agent did. The Tracing tab shows *how
> they were chained*. The edge between them lives in our Python — Foundry
> doesn't model multi-agent topology natively."

---

## 8. Step 6 — HTTP Surface (FastAPI)

Same capabilities, both as deterministic REST and as the LLM-routed `/chat`.

```bash
uvicorn api.main:app --reload --port 8000 --host 0.0.0.0
# Swagger UI: http://localhost:8000/docs
```

| Endpoint | Behaviour |
| --- | --- |
| `POST /agents/ingest` | Upload file or `image_url` → indexes into Azure Search |
| `POST /agents/query`  | `{query, k}` → vector matches |
| `POST /agents/phr`    | Upload image → `{record, explanation}` |
| `POST /agents/chat`   | `{message, thread_id?}` → `{thread_id, reply}` |
| `GET  /healthz`       | Liveness |

Smoke tests:

```bash
curl http://localhost:8000/healthz

curl -X POST http://localhost:8000/agents/query \
     -H 'Content-Type: application/json' \
     -d '{"query":"platelet count","k":3}'

curl -X POST http://localhost:8000/agents/chat \
     -H 'Content-Type: application/json' \
     -d '{"message":"explain sampledata/report1.jpg"}'
```

If `API_KEY` is set in `.env`, add `-H "x-api-key: $API_KEY"` to every call.

### Codespaces port forwarding

VS Code **Ports** panel → port 8000 should auto-appear. Right-click → *Port
Visibility → Public* to share `https://<codespace>-8000.app.github.dev/docs`.
Set `API_KEY` first before going public.

---

## 9. Step 7 — Deploy to Azure Container Apps

```bash
RG=med-doc LOCATION=eastus ACR_NAME=lab2phracr \
ACA_ENV=lab2phr-env APP_NAME=lab2phr-api \
./infra/deploy.sh
# → https://<app>.<region>.azurecontainerapps.io/docs
```

---

## 10. Architecture Story for Q&A

Model split:

1. **GPT-4o** — reasoning, schema extraction, agent orchestration.
2. **Azure AI Vision** — multimodal embeddings for the index.
3. **Azure AI Search** — cheap retrieval.
4. **Azure AI Foundry Agents** — hosted agent definition + thread storage.

Service tradeoff:

- **Document Intelligence** for high-volume, well-structured forms.
- **GPT-4o + agent** when the workflow needs adaptive reasoning or multi-step
  tool use.

Two paths to capability in this repo:

- Deterministic REST (`/ingest`, `/query`, `/phr`) — predictable, scriptable.
- Conversational (`/chat` + ClinicAssistant) — the model picks the tool.

---

## 10b. Google Cloud Equivalents

If you wanted to rebuild this same demo on Google Cloud instead of Azure, the
mapping is fairly clean — every Azure service used here has a near one-to-one
counterpart in the Google ecosystem. The reasoning model (`GPT-4o`) becomes
**Gemini 2.5 Pro / Flash** via either the **Gemini API** (`google-genai` SDK,
fastest to prototype) or **Vertex AI** (`google-cloud-aiplatform`, IAM + VPC
controls for production); both are natively multimodal so `scripts.run_model`
and `scripts.lab_report` collapse into a single `client.models.generate_content`
call that takes the image inline. For the multimodal embeddings step
(`scripts.vectorize_image`), Azure AI Vision is replaced by Vertex AI's
**`multimodalembedding@001`** model, which produces image+text embeddings in a
shared space just like Azure's `vectorizeImage` API. The vector index itself
(Azure AI Search) maps to **Vertex AI Vector Search** (formerly Matching
Engine) for a fully managed ANN index, or **AlloyDB / Cloud SQL with
`pgvector`** if you'd rather keep vectors next to relational data, or
**Firestore vector search** for lighter workloads. The agent layer (Azure AI
Foundry Agents + `runs.create_and_process`) is replaced by the **Agent
Development Kit (ADK)** — an open-source Python framework where you declare
tools as plain functions, hand them to an `LlmAgent`, and let the runner own
the tool-call loop; deployment targets are **Vertex AI Agent Engine** (managed
sessions/threads, the closest analog to Foundry's hosted threads) or **Cloud
Run** for a self-hosted FastAPI wrapper. Storage and hosting round it out:
**Cloud Storage** instead of Blob Storage for the report images, **Cloud Run**
instead of Azure Container Apps for the `/chat` API, and **Application Default
Credentials (`gcloud auth application-default login`)** instead of `az login`
for local auth. The Python tool functions in `scripts/` would barely change —
only the client construction at the top of each file.

| This repo (Azure) | Google Cloud equivalent |
| --- | --- |
| Azure OpenAI GPT-4o | Gemini 2.5 Pro/Flash via Gemini API or Vertex AI |
| Azure AI Vision multimodal embeddings | Vertex AI `multimodalembedding@001` |
| Azure AI Search (vector index) | Vertex AI Vector Search / `pgvector` on AlloyDB |
| Azure AI Foundry Agents + threads | ADK `LlmAgent` + Vertex AI Agent Engine sessions |
| Azure Blob Storage | Cloud Storage |
| Azure Container Apps | Cloud Run |
| `az login` (AAD) | `gcloud auth application-default login` (ADC) |

## 11. Stage Safety Checklist

1. Run `python -m scripts.run_model` once before the session starts.
2. Keep 3–4 known images in `sampledata/` plus one backup.
3. Confirm the search index exists and `AZURE_SEARCH_QUERY_KEY` works.
4. `az login` is current; `AZURE_AI_PROJECT_ENDPOINT` reachable.
5. Have one fallback command per step visible in notes.
6. Rotate keys after the event.

---

## 12. Cost & Pricing (approximate)

> All numbers below are **rough public list prices in USD as of late 2025**
> for the `eastus` / `eastus2` regions. Always check the official Azure
> pricing pages before quoting customers — prices change and vary by region,
> tier, and commitment.

### 12.1 Per-component cost

| Component | What you pay for | Approx. list price | Demo footprint |
| --- | --- | --- | --- |
| **Azure OpenAI — GPT-4o** | Input + output tokens | ~$2.50 / 1M input, ~$10 / 1M output tokens | A full demo run (vision + extract + explain over a few reports) is well under **$0.10**. |
| **Azure OpenAI — GPT-4o image input** | Tiles per image (depends on resolution) | ~$0.001–0.005 per lab image | Negligible for a handful of images. |
| **Azure AI Vision — multimodal embeddings** | Per 1,000 transactions (`vectorizeImage` / `vectorizeText`) | **S1 tier ~$1 per 1,000 calls** | Indexing 10 reports + a few queries ≈ **$0.02**. |
| **Azure AI Search** | Hourly per replica/partition + storage | **Basic ~$75 / month**, Free tier $0 (1 index, 50 MB) | Use **Free tier** for the demo — $0. |
| **Azure AI Foundry (Agents)** | Underlying model tokens + thread storage | Tokens billed via Azure OpenAI; thread storage negligible at demo volume | Effectively the same as the GPT-4o line above. |
| **Azure Blob Storage** (optional, for `/ingest` from URL) | GB-month + transactions | **Hot LRS ~$0.018 / GB-month**, ~$0.004 per 10K reads | Pennies. |
| **Azure Container Registry** | Per registry per day | **Basic ~$0.167 / day (~$5 / month)** + storage | ~$5 / month if left running. |
| **Azure Container Apps** | vCPU-second + GiB-second + requests; generous free grant | First **180,000 vCPU-s + 360,000 GiB-s + 2M requests free per month**; then ~$0.000024 / vCPU-s | A demo app idling at min-replicas=0 is **$0**; a small always-on replica is ~$15–30 / month. |
| **Azure Monitor / Log Analytics** (auto-enabled by ACA) | GB ingested | ~$2.30 / GB ingested, 5 GB free | Negligible for demo traffic. |

**Bottom line for a single live demo session:** under **$1** of consumption if
you start from a clean state, use the AI Search Free tier, and tear things
down afterward. Leaving the **Basic AI Search tier** running is by far the
biggest silent cost (~$75/month), followed by **ACR Basic** (~$5/month).

### 12.2 What to watch out for

- **AI Search Basic** bills hourly whether you query it or not — switch to
  **Free** for demos, or delete the service after the event.
- **Container Apps** with `min-replicas >= 1` keeps a vCPU warm 24/7. Set
  `--min-replicas 0` to scale to zero between demos.
- **GPT-4o vision** cost scales with image **resolution** (more tiles = more
  tokens). Downscale lab images before sending if cost matters.
- **Foundry threads** persist until deleted — fine for demo, but clean up if
  PHI ever touched them.

Official pricing references (verify before quoting):
- <https://azure.microsoft.com/pricing/details/cognitive-services/openai-service/>
- <https://azure.microsoft.com/pricing/details/cognitive-services/computer-vision/>
- <https://azure.microsoft.com/pricing/details/search/>
- <https://azure.microsoft.com/pricing/details/container-apps/>
- <https://azure.microsoft.com/pricing/details/container-registry/>
- <https://azure.microsoft.com/pricing/details/storage/blobs/>

---

## 13. Cleanup

The cheapest way to stop the meter is to **delete the resource group** — it
removes ACR, the Container Apps environment, the app, AI Search, Log
Analytics, and any storage accounts in one shot.

### 13.1 Nuke the whole demo RG

```bash
# Replace with the RG you used in section 9.
RG=med-doc
az group delete -n "$RG" --yes --no-wait
```

> `--no-wait` returns immediately; deletion runs in the background. Confirm
> later with `az group exists -n "$RG"` (should print `false`).

### 13.2 Selective cleanup (keep the RG)

If the RG is shared with other workloads, delete only the demo resources:

```bash
RG=med-doc
APP_NAME=lab2phr-api
ACA_ENV=lab2phr-env
ACR_NAME=lab2phracr
SEARCH_NAME=<your-search-service>      # from AZURE_SEARCH_ENDPOINT
OPENAI_NAME=<your-openai-resource>     # from ENDPOINT_URL
FOUNDRY_PROJECT=<your-foundry-project> # from AZURE_AI_PROJECT_ENDPOINT

az containerapp delete       -g "$RG" -n "$APP_NAME"     --yes
az containerapp env delete   -g "$RG" -n "$ACA_ENV"      --yes
az acr delete                -g "$RG" -n "$ACR_NAME"     --yes
az search service delete     -g "$RG" -n "$SEARCH_NAME"  --yes
# Azure OpenAI + Foundry are Cognitive Services accounts:
az cognitiveservices account delete -g "$RG" -n "$OPENAI_NAME"
az cognitiveservices account delete -g "$RG" -n "$FOUNDRY_PROJECT"
```

> Cognitive Services accounts go into a **soft-delete** state for 48 hours.
> To free the name immediately:
> `az cognitiveservices account purge -g "$RG" -n "$OPENAI_NAME" -l <region>`

### 13.3 Foundry agents and threads

If you reuse the Foundry project but want to clear demo agents/threads:

- ai.azure.com → your project → **Agents** → delete `clinic-assistant`.
- ai.azure.com → your project → **Threads** → delete demo thread IDs.

### 13.4 Search index only (keep the service)

```bash
python -m scripts.clear_index    # drops all docs from the configured index
```

### 13.5 Local cleanup

```bash
deactivate 2>/dev/null || true
rm -rf .venv __pycache__ */__pycache__
# Rotate any keys that were pasted into .env during the demo.
```

### 13.6 Final sanity check

```bash
az group exists -n "$RG"                # expect: false
az cognitiveservices account list -g "$RG" 2>/dev/null   # expect: empty / RG gone
```


