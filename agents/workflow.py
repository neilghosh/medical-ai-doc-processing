"""Multi-agent workflow demo (functional style).

Two agents wired as plain async functions:
    user query -> query_agent (vector-search) -> summarizer_agent (extract + explain)

The first agent's *output* (a file path) becomes the second agent's *input*.

    python -m agents.workflow "Summarise the CBC report"
"""
import argparse
import asyncio
import atexit
import logging
import os
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning, message=r".*AzureAIAgentClient is deprecated.*")

from dotenv import load_dotenv

from agent_framework import WorkflowBuilder, WorkflowContext, executor
from agent_framework.observability import enable_instrumentation
from agent_framework_azure_ai import AzureAIAgentClient
from azure.identity.aio import DefaultAzureCredential

from scripts.phr_extractor import explain, extract
from scripts.query_index import search


def _setup_tracing() -> None:
    """Send agent + tool spans to App Insights (Foundry Tracing tab). No-op if unset."""
    if not os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        return
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor  # type: ignore[import-not-found]
        configure_azure_monitor(disable_logging=True)
        # enable_sensitive_data=True records full prompts + completions. Demo-only.
        enable_instrumentation(enable_sensitive_data=True)
        # OTel attaches a LoggingHandler whose .flush() spawns a thread; remove it
        # before interpreter shutdown to avoid a benign atexit traceback.
        atexit.register(lambda: [logging.root.removeHandler(h)
                                 for h in list(logging.root.handlers)
                                 if "opentelemetry" in type(h).__module__])
        print("[tracing] -> Azure App Insights (Foundry Tracing tab)")
    except Exception as e:
        print(f"[tracing] disabled ({type(e).__name__}: {e})")


async def run_workflow(prompt: str) -> None:
    model = os.environ.get("AGENT_MODEL_DEPLOYMENT") or os.environ["DEPLOYMENT_NAME"]
    endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]

    async with (
        DefaultAzureCredential() as cred,
        AzureAIAgentClient(project_endpoint=endpoint, model_deployment_name=model,
                           credential=cred, agent_name="query_agent",
                           should_cleanup_agent=False) as query_client,
        AzureAIAgentClient(project_endpoint=endpoint, model_deployment_name=model,
                           credential=cred, agent_name="summarizer_agent",
                           should_cleanup_agent=False) as summarizer_client,
    ):
        query_agent = query_client.as_agent(
            name="query_agent",
            instructions="Call search(query, k=1). Reply with ONLY the file_path of the top match.",
            tools=[search],
        )
        summarizer_agent = summarizer_client.as_agent(
            name="summarizer_agent",
            instructions=(
                "Call extract(image_path) then explain(record). "
                "Answer the user's question from the report; add a doctor disclaimer."
            ),
            tools=[extract, explain],
        )

        @executor(id="query")
        async def run_query(user_prompt: str, ctx: WorkflowContext[tuple[str, str]]) -> None:
            print(f"\n>> query_agent      <- {user_prompt!r}")
            resp = await query_agent.run(user_prompt)
            file_path = resp.text.strip().strip("`'\"")
            print(f"<< query_agent      -> {file_path}")
            await ctx.send_message((user_prompt, file_path))

        @executor(id="summarize")
        async def run_summarize(payload: tuple[str, str], ctx: WorkflowContext[None, str]) -> None:
            user_prompt, file_path = payload
            print(f"\n>> summarizer_agent <- {file_path}")
            resp = await summarizer_agent.run(
                f"Report path: {file_path}\nUser question: {user_prompt}"
            )
            print(f"<< summarizer_agent -> {resp.text[:120]}...")
            await ctx.yield_output(resp.text)

        workflow = (WorkflowBuilder(start_executor=run_query)
                    .add_edge(run_query, run_summarize).build())

        print(f"[workflow] query -> summarize    input={prompt!r}")
        result = await workflow.run(prompt)

        print("\n[final output]")
        for out in result.get_outputs():
            print(out)
        print(f"\n[Foundry agents]  query_agent={query_client.agent_id}  "
              f"summarizer_agent={summarizer_client.agent_id}")


def main() -> None:
    load_dotenv()
    _setup_tracing()
    parser = argparse.ArgumentParser(description="Functional multi-agent workflow demo.")
    parser.add_argument("prompt", nargs="+", help="User query (e.g. 'summarise the CBC report').")
    args = parser.parse_args()
    asyncio.run(run_workflow(" ".join(args.prompt)))


if __name__ == "__main__":
    main()
