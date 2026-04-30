"""OrchestratorAgent — single agent that owns all four tools.

Same agent definition runs locally and in Foundry: the SDK's
`runs.create_and_process(...)` automatically executes the FunctionTools in the
caller's process when the run requires action.
"""
from azure.ai.agents.models import FunctionTool, ToolSet

from agents.core.azure_clients import get_agents_client, get_model
from scripts.ingest_reports import ingest
from scripts.phr_extractor import explain, extract
from scripts.query_index import search

INSTRUCTIONS = (
    "You are the OrchestratorAgent for a medical lab-report assistant. "
    "Pick the right tool based on user intent:\n"
    "- ingest(path): user wants to add/index/upload a report image or folder.\n"
    "- search(query, k): user asks which report contains something (clinical question).\n"
    "- extract(image_path): user wants a structured PHR JSON for a specific report image.\n"
    "- explain(record): summarise a PHR JSON record in plain language.\n"
    "Rules:\n"
    "1. If the user asks a clinical question without naming a file, call search first.\n"
    "2. To explain a report, you MUST first call extract(image_path) and then call "
    "explain(record=<the JSON object returned by extract>). Never call explain "
    "without passing the record argument.\n"
    "3. Always state which tool(s) you used."
)


def build():
    toolset = ToolSet()
    toolset.add(FunctionTool(functions={ingest, search, extract, explain}))
    agents = get_agents_client()
    agents.enable_auto_function_calls(toolset)
    return agents.create_agent(
        model=get_model(),
        name="orchestrator-agent",
        instructions=INSTRUCTIONS,
        toolset=toolset,
    )
