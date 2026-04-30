"""REPL against the Foundry-hosted OrchestratorAgent.

Tools (FunctionTool) execute in this process via `runs.create_and_process`,
which automatically handles the requires_action/submit_tool_outputs loop.

    python -m agents.chat
"""
import os
import sys

from dotenv import load_dotenv
from azure.ai.agents.models import FunctionTool, ToolSet

from agents.core.azure_clients import get_agents_client
from scripts.ingest_reports import ingest
from scripts.phr_extractor import explain, extract
from scripts.query_index import search


def _print_latest_assistant(agents, thread_id):
    for m in agents.messages.list(thread_id=thread_id):
        if m.role != "assistant":
            continue
        for part in m.content:
            text = getattr(part, "text", None)
            value = getattr(text, "value", None) if text else None
            if value:
                print(value)
        return


def main() -> None:
    load_dotenv()
    agent_id = os.environ.get("ORCHESTRATOR_AGENT_ID")
    if not agent_id:
        print("ORCHESTRATOR_AGENT_ID not set. Run `python -m agents.bootstrap_agents` first.",
              file=sys.stderr)
        sys.exit(2)

    agents = get_agents_client()
    # Register the local Python tool functions so create_and_process can invoke
    # them when the run hits requires_action.
    toolset = ToolSet()
    toolset.add(FunctionTool(functions={ingest, search, extract, explain}))
    agents.enable_auto_function_calls(toolset)

    thread = agents.threads.create()
    print(f"[chat] thread_id={thread.id} orchestrator={agent_id}")
    print("Type a message ('exit' or Ctrl-D to quit).\n")

    while True:
        try:
            user = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user or user.lower() in {"exit", "quit"}:
            break
        agents.messages.create(thread_id=thread.id, role="user", content=user)
        run = agents.runs.create_and_process(thread_id=thread.id, agent_id=agent_id)
        if run.status != "completed":
            print(f"[run {run.status}] {getattr(run, 'last_error', None)}")
            continue
        print("orchestrator>")
        _print_latest_assistant(agents, thread.id)
        print()


if __name__ == "__main__":
    main()
