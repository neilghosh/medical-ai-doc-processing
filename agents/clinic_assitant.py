"""ClinicAssistant — one-shot agent run.

Creates the agent, sends a single prompt, prints the reply. By default a fresh
thread is created; pass --thread <id> to continue an existing conversation.

    python -m agents.clinic_assitant "summarise the latest CBC report"
    python -m agents.clinic_assitant --thread thread_abc123 "and the WBC?"
"""
import argparse
import logging
import os

from dotenv import load_dotenv
from azure.ai.agents.models import FunctionTool, ToolSet
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

# Demo: always dump raw agent/thread/run HTTP traffic to stdout.
logging.basicConfig(level=logging.DEBUG)
logging.getLogger(
    "azure.core.pipeline.policies.http_logging_policy"
).setLevel(logging.DEBUG)

from scripts.ingest_reports import ingest
from scripts.phr_extractor import explain, extract
from scripts.query_index import search

INSTRUCTIONS = (
    "You are ClinicAssistant, a medical lab-report helper. "
    "Pick the right tool based on user intent:\n"
    "- ingest(path): add/index/upload a report image or folder.\n"
    "- search(query, k): clinical question without a named file.\n"
    "- extract(image_path): structured PHR JSON for a specific report image.\n"
    "- explain(record): plain-language summary of a PHR JSON record.\n"
    "To explain a report, first call extract(image_path), then call "
    "explain(record=<JSON returned by extract>). Always say which tool you used.\n"
    "IMPORTANT: You are NOT a certified doctor. If the user asks for medical "
    "advice, diagnosis, treatment, or medication recommendations, decline and "
    "tell them to consult a licensed physician. Whenever you explain a report, "
    "append a disclaimer: 'This explanation is AI-generated; please consult a "
    "real doctor to review it.'"
)


def build_clinic_assistant():
    """Create the ClinicAssistant agent and return (agents_client, agent)."""
    project = AIProjectClient(
        endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        credential=DefaultAzureCredential(),
        logging_enable=True,
    )
    agents = project.agents

    toolset = ToolSet()
    toolset.add(FunctionTool(functions={ingest, search, extract, explain}))
    agents.enable_auto_function_calls(toolset)

    model = os.environ.get("AGENT_MODEL_DEPLOYMENT") or os.environ["DEPLOYMENT_NAME"]
    agent = agents.create_agent(
        model=model,
        name="clinic-assistant",
        instructions=INSTRUCTIONS,
        toolset=toolset,
    )
    return agents, agent


def latest_assistant_text(agents, thread_id) -> str:
    for m in agents.messages.list(thread_id=thread_id):
        if m.role == "assistant":
            return "\n".join(p.text.value for p in m.content if getattr(p, "text", None))
    return ""


def print_latest_assistant(agents, thread_id):
    print(latest_assistant_text(agents, thread_id))


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="One-shot ClinicAssistant call.")
    parser.add_argument("--thread", help="Existing thread id to continue.")
    parser.add_argument("prompt", nargs="+", help="Your message to the assistant.")
    args = parser.parse_args()
    prompt = " ".join(args.prompt)

    agents, agent = build_clinic_assistant()
    thread = agents.threads.get(args.thread) if args.thread else agents.threads.create()
    print(f"[clinic-assistant] agent_id={agent.id} thread_id={thread.id}")

    agents.messages.create(thread_id=thread.id, role="user", content=prompt)
    run = agents.runs.create_and_process(thread_id=thread.id, agent_id=agent.id)
    if run.status != "completed":
        print(f"[run {run.status}] {getattr(run, 'last_error', None)}")
        return
    print_latest_assistant(agents, thread.id)


if __name__ == "__main__":
    main()
