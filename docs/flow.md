# Lab2PHR — Detailed Flow

Internals of the conversational path: how a thread is reused turn-after-turn,
how the agent loop drives tool calls, and where state lives.

---

## 1. Agent loop on a reused thread

The model is **stateless per call**. A "conversation" is just a thread on the
server side that we keep appending to and replaying.

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant API as FastAPI /agents/chat
    participant Agents as Foundry Agents API
    participant Thread as Thread store
    participant LLM as GPT-4o
    participant Tool as Local Python tool
    participant Search as Azure AI Search
    participant Blob as Azure Blob Storage

    User->>API: POST message and optional thread_id
    alt new conversation
        API->>Agents: threads.create
        Agents->>Thread: INSERT thread row
        Agents-->>API: thread_id
    else continue
        Note over API,Thread: thread_id reused - full history on server
    end

    API->>Agents: messages.create user message
    Agents->>Thread: APPEND user message

    API->>Agents: runs.create_and_process
    Agents->>Thread: SELECT all messages
    Agents->>LLM: system + history + tools schema

    loop until run completed
        LLM-->>Agents: assistant message OR tool call
        alt tool call
            Agents->>Thread: APPEND assistant tool_call
            Agents-->>API: requires_action
            API->>Tool: invoke matching Python fn
            Tool->>Search: vector or keyword query
            Tool->>Blob: optional read for ingest
            Tool->>LLM: GPT-4o vision call
            Tool-->>API: result JSON
            API->>Agents: submit_tool_outputs
            Agents->>Thread: APPEND tool message
            Agents->>LLM: replay history + tool outputs
        else final assistant text
            Agents->>Thread: APPEND assistant message
        end
    end

    API->>Agents: messages.list
    Agents->>Thread: SELECT newest assistant message
    Agents-->>API: text
    API-->>User: thread_id and reply
```

### What "send the full context" means

Each iteration of the loop, Foundry rebuilds the prompt by reading every
message ever written to that `thread_id` (system instructions + every user,
assistant, and tool message). That blob is what gets sent to GPT-4o. The
client never has to re-send prior turns — passing `thread_id` is enough,
because the server already has them.

---

## 2. Two SDK shapes for "remembering the conversation"

### 2a. Chat Completions API (classic; what most providers expose)

```mermaid
sequenceDiagram
    participant App
    participant LLM as Chat Completions

    App->>App: build messages = system + prior turns + new user
    App->>LLM: POST /chat/completions with messages and tools
    LLM-->>App: assistant message
    App->>App: append assistant message to local history
```

- The server holds **no state**.
- The app must store every turn somewhere (DB, Redis, memory) and resend the
  whole array on every call.
- Token cost grows with history length unless the app trims/summarises.

### 2b. Responses API (newer; Foundry Agents threads work this way)

```mermaid
sequenceDiagram
    participant App
    participant Agents as Foundry Agents
    participant Thread as Thread server-side

    App->>Agents: messages.create thread_id and text
    App->>Agents: runs.create_and_process thread_id and agent_id
    Note over Agents,Thread: Server reads thread, calls model, writes assistant back
    Agents-->>App: run completed
    App->>Agents: messages.list returns latest assistant text
```

- The server holds the conversation. The client sends only `(thread_id,
  new_message)`.
- Agent definition (model + instructions + tools) is reused across users;
  threads provide isolation.
- Same `thread_id` in a later process resumes the exact same context — that
  is what `python -m agents.clinic_assitant --thread <id>` does.

---

## 3. Where state actually lives

```mermaid
flowchart LR
    subgraph Foundry["Azure AI Foundry project"]
        AgentDef["Agent definition<br/>(model + instructions + tool schemas)"]
        ThreadStore[("Thread + message store<br/>Cosmos DB-style document store,<br/>managed by Foundry")]
        Runs[("Run + step records<br/>(status, tool_calls, tool_outputs)")]
    end

    subgraph SearchSvc["Azure AI Search"]
        Index[("Vector index<br/>id, file_path, image_vector")]
    end

    subgraph Storage["Azure Blob Storage"]
        Blob[("Source images<br/>e.g. sampledata/*.jpg")]
    end

    subgraph App["Our process"]
        ScriptsBox["scripts/* functions<br/>(ingest, search, extract, explain)"]
    end

    ScriptsBox -- "vectorise + upload<br/>(ingest_blob_container.py)" --> Index
    Index -- "stores file_path<br/>pointing back to blob" --> Blob
    ScriptsBox -- "search() reads<br/>nearest-neighbour ids" --> Index
    ScriptsBox -- "extract/explain pull image bytes" --> Blob

    AgentDef --- ThreadStore
    ThreadStore --- Runs
```

### Concretely

- **Threads / messages / runs** are persisted by the Foundry Agents service.
  Microsoft hasn't published the underlying engine name; the externally
  observable behaviour is a Cosmos-DB-style document store keyed by
  `thread_id` and `run_id`. You don't manage it — visible in *AI Foundry
  portal → your project → Agents / Threads*.
- **AI Search index** stores the embedding (`image_vector`) plus a tiny
  payload (`id`, `file_path`). The vector lets us do k-NN; the `file_path`
  is a pointer back to the original blob.
- **Blob Storage** holds the source images. `scripts.ingest_blob_container`
  walks a container, generates the embedding via Azure AI Vision, and writes
  one Search doc per image. Later `extract` / `explain` can fetch the bytes
  again from blob (or work from a local path if running on the same machine).
- **Our app** holds nothing across requests — every Python process talks to
  the three Azure services above for state.

---

## 4. End-to-end — "explain sampledata/report1.jpg" on a fresh thread

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant API
    participant Agents as Foundry Agents
    participant LLM as GPT-4o
    participant Extract as scripts.phr_extractor.extract
    participant Explain as scripts.phr_extractor.explain

    User->>API: POST /agents/chat - explain sampledata/report1.jpg
    API->>Agents: threads.create returns t1
    API->>Agents: messages.create t1 user
    API->>Agents: runs.create_and_process t1 agent

    Agents->>LLM: history + tool schemas
    LLM-->>Agents: tool_call extract
    Agents-->>API: requires_action
    API->>Extract: extract sampledata/report1.jpg
    Extract->>LLM: vision call returns JSON record
    Extract-->>API: record
    API->>Agents: submit_tool_outputs record

    Agents->>LLM: history + tool_output record
    LLM-->>Agents: tool_call explain
    Agents-->>API: requires_action
    API->>Explain: explain record
    Explain->>LLM: chat call returns plain-language summary
    Explain-->>API: text
    API->>Agents: submit_tool_outputs text

    Agents->>LLM: history + tool_output text
    LLM-->>Agents: final assistant message with disclaimer
    Agents-->>API: run completed
    API-->>User: thread_id t1 and reply
```

A follow-up call with the same `thread_id` skips steps 2–3 and resumes from
the existing history — the model already "remembers" what the report said.
