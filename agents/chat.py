"""Interactive REPL against ClinicAssistant on a single shared thread.

Tools (FunctionTool) execute in this process via `runs.create_and_process`,
which handles the requires_action/submit_tool_outputs loop. The thread is
reused across turns so the assistant retains conversation context.

    python -m agents.chat
"""
from dotenv import load_dotenv

from agents.clinic_assitant import build_clinic_assistant, print_latest_assistant


def main() -> None:
    load_dotenv()
    agents, agent = build_clinic_assistant()
    thread = agents.threads.create()
    print(f"[chat] agent_id={agent.id} thread_id={thread.id}")
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
        run = agents.runs.create_and_process(thread_id=thread.id, agent_id=agent.id)
        if run.status != "completed":
            print(f"[run {run.status}] {getattr(run, 'last_error', None)}")
            continue
        print("clinic-assistant>")
        print_latest_assistant(agents, thread.id)
        print()


if __name__ == "__main__":
    main()
