"""FastAPI app exposing the Lab2PHR agents over HTTPS.

Endpoints:
    POST /agents/ingest  — upload or URL an image to be indexed
    POST /agents/query   — vector-search the index for a clinical question
    POST /agents/phr     — extract + explain a single lab-report image
    POST /agents/chat    — converse with the OrchestratorAgent (Foundry hosted)
    GET  /healthz        — liveness probe
    GET  /docs           — auto-generated OpenAPI/Swagger UI
"""
from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()

from scripts.ingest_reports import ingest  # noqa: E402
from scripts.phr_extractor import explain, extract  # noqa: E402
from scripts.query_index import search  # noqa: E402
from api.images import materialize_image  # noqa: E402
from api.run_loop import latest_assistant_text, run_thread  # noqa: E402


app = FastAPI(
    title="Lab2PHR Agents API",
    version="1.0.0",
    description="HTTP surface for the medical-report Ingest / Query / PHR / Orchestrator agents.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Optional API-key gate
# ---------------------------------------------------------------------------
def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    expected = os.environ.get("API_KEY")
    if not expected:
        return
    if x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing x-api-key header.")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class QueryRequest(BaseModel):
    query: str = Field(..., description="Clinical question, e.g. 'report with HBA1C'.")
    k: int = Field(default=5, ge=1, le=20)


class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------
@app.post("/agents/ingest", dependencies=[Depends(require_api_key)])
async def ingest_endpoint(
    file: Optional[UploadFile] = File(default=None),
    image_url: Optional[str] = Form(default=None),
) -> dict:
    path = await materialize_image(file=file, image_url=image_url)
    return await run_in_threadpool(ingest, path)


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------
@app.post("/agents/query", dependencies=[Depends(require_api_key)])
async def query_endpoint(req: QueryRequest) -> dict:
    matches = await run_in_threadpool(search, req.query, req.k)
    return {"query": req.query, "matches": matches}


# ---------------------------------------------------------------------------
# PHR
# ---------------------------------------------------------------------------
@app.post("/agents/phr", dependencies=[Depends(require_api_key)])
async def phr_endpoint(
    file: Optional[UploadFile] = File(default=None),
    image_url: Optional[str] = Form(default=None),
) -> dict:
    path = await materialize_image(file=file, image_url=image_url)
    record = await run_in_threadpool(extract, path)
    explanation = await run_in_threadpool(explain, record)
    return {"record": record, "explanation": explanation}


# ---------------------------------------------------------------------------
# Chat with Foundry-hosted orchestrator
# ---------------------------------------------------------------------------
@app.post("/agents/chat", dependencies=[Depends(require_api_key)])
async def chat_endpoint(req: ChatRequest) -> dict:
    agent_id = os.environ.get("ORCHESTRATOR_AGENT_ID")
    if not agent_id:
        raise HTTPException(
            status_code=503,
            detail="ORCHESTRATOR_AGENT_ID not set. Run agents.bootstrap_agents first.",
        )
    timeout_s = int(os.environ.get("AGENT_RUN_TIMEOUT_S", "90"))

    # Lazy import so the API can boot without Foundry creds for health checks.
    from azure.ai.agents.models import FunctionTool, ToolSet
    from agents.core.azure_clients import get_agents_client

    agents = get_agents_client()
    # Register the local Python tools so create_and_process can invoke them
    # when the run hits requires_action.
    toolset = ToolSet()
    toolset.add(FunctionTool(functions={ingest, search, extract, explain}))
    agents.enable_auto_function_calls(toolset)

    def _do() -> dict:
        thread_id = req.thread_id
        if not thread_id:
            thread_id = agents.threads.create().id
        agents.messages.create(thread_id=thread_id, role="user", content=req.message)
        run = run_thread(agents, thread_id, agent_id, timeout_s=timeout_s)
        status = getattr(run, "status", None) or run.get("status")
        if status != "completed":
            raise HTTPException(status_code=502, detail=f"Run {status}")
        return {"thread_id": thread_id, "reply": latest_assistant_text(agents, thread_id)}

    return await run_in_threadpool(_do)
