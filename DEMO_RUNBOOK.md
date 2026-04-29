# Lab2PHR Demo Runbook

This is a simple, stage-friendly runbook from a fresh VS Code launch to a full agentic architecture story.

## 1. Launch and Setup (2-3 minutes)

1. Open the project in VS Code.
2. Open terminal in project root.
3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Check `.env` contains at least:
- `ENDPOINT_URL`
- `DEPLOYMENT_NAME`
- `AZURE_OPENAI_API_KEY`
- `AZURE_SEARCH_ENDPOINT`
- `AZURE_SEARCH_KEY`
- `AZURE_SEARCH_QUERY_KEY`

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
