"""Drive a Foundry agent run to completion.

The single OrchestratorAgent owns FunctionTools. `runs.create_and_process`
automatically executes them in this process when the run hits
`requires_action`. The caller must register the same toolset on the agents
client via `enable_auto_function_calls` (done once in api.main).
"""
from __future__ import annotations

from typing import Any


def run_thread(agents, thread_id: str, agent_id: str, timeout_s: int = 90) -> Any:
    return agents.runs.create_and_process(thread_id=thread_id, agent_id=agent_id)


def latest_assistant_text(agents, thread_id: str) -> str:
    for m in agents.messages.list(thread_id=thread_id):
        role = getattr(m, "role", None) or m.get("role")
        if role != "assistant":
            continue
        content = getattr(m, "content", None) or m.get("content", [])
        chunks: list[str] = []
        for part in content:
            text = getattr(part, "text", None)
            if text is None and isinstance(part, dict):
                text = part.get("text")
            if text is None:
                continue
            value = getattr(text, "value", None) if hasattr(text, "value") else text.get("value")
            if value:
                chunks.append(value)
        return "\n".join(chunks)
    return ""
