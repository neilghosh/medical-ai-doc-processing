# Lab2PHR Architecture

Two personas, two paths to the same capability functions.

```mermaid
flowchart LR
    User([End user])
    Dev([Developer])

    subgraph API["FastAPI (api/main.py)"]
        Ingest["POST /agents/ingest"]
        Query["POST /agents/query"]
        Phr["POST /agents/phr"]
        Chat["POST /agents/chat"]
    end

    subgraph Agent["ClinicAssistant agent (Foundry)"]
        Tools["FunctionTool set:<br/>ingest · search · extract · explain"]
    end

    subgraph Scripts["scripts/ — capability functions"]
        S_Ingest["ingest_reports.ingest"]
        S_Search["query_index.search"]
        S_Extract["phr_extractor.extract"]
        S_Explain["phr_extractor.explain"]
    end

    subgraph Azure["Azure services"]
        Search[("Azure AI Search<br/>vector index")]
        Vision["Azure AI Vision<br/>image embeddings"]
        LLM["Foundry-hosted GPT-4o"]
    end

    %% User → API
    User --> Ingest
    User --> Query
    User --> Phr
    User --> Chat

    %% Deterministic REST calls scripts directly
    Ingest --> S_Ingest
    Query  --> S_Search
    Phr    --> S_Extract
    Phr    --> S_Explain

    %% Conversational path: API → agent → tools → scripts
    Chat --> Agent
    Agent --> Tools
    Tools --> S_Ingest
    Tools --> S_Search
    Tools --> S_Extract
    Tools --> S_Explain

    %% Scripts → Azure
    S_Ingest --> Vision
    S_Ingest --> Search
    S_Search --> Search
    S_Extract --> LLM
    S_Explain --> LLM

    %% Developer bypasses everything
    Dev -. "python -m scripts.X" .-> Scripts
    Dev -. "python -m agents.chat / .clinic_assitant" .-> Agent
```

## Flows

**End user → REST (deterministic).**
`/ingest` vectorises an image via Azure AI Vision and writes it to the AI
Search index. `/query` runs vector k-NN against the same index. `/phr`
extracts a structured PHR JSON from a single image with GPT-4o, then asks the
model to explain it.

**End user → `/chat` (conversational).**
The request lands on the FastAPI endpoint, which forwards the message to the
`clinic-assistant` agent in Foundry. The agent decides which of the four
FunctionTools to invoke; `runs.create_and_process` executes the matching
Python function locally, submits the result back, and loops until the run
completes. Threads keep per-conversation memory.

**Developer.**
Skips both layers: runs the underlying scripts directly
(`python -m scripts.query_index`) for fast local verification, or talks to the
agent over the CLI/REPL (`python -m agents.clinic_assitant`,
`python -m agents.chat`) without going through HTTP.

## Why two paths

- REST endpoints are predictable and scriptable — good for pipelines and
  integration tests.
- The `/chat` agent path lets the model pick the tool — good for free-form
  user questions without writing routing code.
- Both call the *same* `scripts/` functions, so capability changes happen in
  one place.
