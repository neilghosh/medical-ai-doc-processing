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

## 11. Stage Safety Checklist

1. Run `python -m scripts.run_model` once before the session starts.
2. Keep 3–4 known images in `sampledata/` plus one backup.
3. Confirm the search index exists and `AZURE_SEARCH_QUERY_KEY` works.
4. `az login` is current; `AZURE_AI_PROJECT_ENDPOINT` reachable.
5. Have one fallback command per step visible in notes.
6. Rotate keys after the event.

