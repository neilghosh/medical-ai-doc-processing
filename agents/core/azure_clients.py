"""Azure AI Foundry project client (used by agent factories and chat REPL)."""
import os
from functools import lru_cache


@lru_cache(maxsize=1)
def get_agents_client():
    """`.agents` sub-client of the Foundry project (AAD via DefaultAzureCredential)."""
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    project = AIProjectClient(
        endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        credential=DefaultAzureCredential(),
    )
    return project.agents


def get_model() -> str:
    """Model deployment to bind agents to."""
    return os.environ.get("AGENT_MODEL_DEPLOYMENT") or os.environ["DEPLOYMENT_NAME"]
