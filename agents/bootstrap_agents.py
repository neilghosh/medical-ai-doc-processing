"""Create (or reuse) the single OrchestratorAgent and write its id.

    python -m agents.bootstrap_agents
"""
import json
from pathlib import Path

from dotenv import load_dotenv

from agents import clinic_assitant
from agents.core.azure_clients import get_agents_client

load_dotenv()


def _id(obj):
    return getattr(obj, "id", None) or obj["id"]


def _find(agents, name):
    for a in agents.list_agents():
        if (getattr(a, "name", None) or a.get("name")) == name:
            return a
    return None


def main() -> None:
    agents = get_agents_client()
    existing = _find(agents, "orchestrator-agent")
    if existing:
        agents.delete_agent(_id(existing))
    agent_id = _id(clinic_assitant.build())
    print(f"[created] orchestrator-agent -> {agent_id}")

    Path(".agents.json").write_text(json.dumps({"orchestrator": agent_id}, indent=2))
    print("\nExport into .env:")
    print(f"ORCHESTRATOR_AGENT_ID={agent_id}")


if __name__ == "__main__":
    main()

