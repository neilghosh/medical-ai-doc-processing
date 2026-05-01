# Copilot instructions for this repo

This is a **demo / teaching** repo. Optimize for code that is short, obvious,
and easy to read on stage. Performance is secondary.

## Style preferences

- **Minimalism over cleverness.** Fewer files, fewer abstractions, fewer
  layers. Inline simple logic instead of wrapping it in helpers.
- **No premature optimization.** Skip caching (`lru_cache`, memoization),
  pooling, or lazy-init unless the demo is visibly slow without it. It is OK
  if a script re-creates an Azure client or even a Foundry agent on every
  invocation — explicit is better than hidden state.
- **No defensive over-engineering.** Don't add error handling for cases that
  can't happen, don't validate inputs except at clear system boundaries
  (HTTP, CLI), and don't add docstrings/type hints to code we didn't change.
- **Don't add features that weren't asked for.** No "while I'm here"
  refactors. No new helper modules unless the same code is genuinely repeated
  3+ times.

## Patterns we prefer

- **CLI argument parsing:** use `argparse` instead of hand-rolled
  `sys.argv` slicing. It handles `--flag value`, `--flag=value`, `-h`, and
  errors for free with the same number of lines.
- **Env vars:** read with `os.environ["KEY"]` (KeyError is fine for required)
  or `os.environ.get("KEY", default)` for optional. Always `load_dotenv()` at
  the top of `main()`.
- **Foundry agent SDK:** use `runs.create_and_process(...)` — it owns the
  requires_action / submit_tool_outputs polling loop. Don't reimplement it.
- **Threads vs agents:** an agent is a reusable definition (model +
  instructions + tools); per-conversation isolation belongs on the **thread**,
  not the agent. For demos it's fine to create a new agent per call; for
  reuse, look up by name.
- **FastAPI endpoints:** wrap blocking SDK calls with
  `fastapi.concurrency.run_in_threadpool` rather than rewriting them async.
- **Two paths to capability:** keep deterministic REST endpoints (`/ingest`,
  `/query`, `/phr`) alongside the LLM-routed `/chat` endpoint. Both call the
  same underlying Python tool functions in `scripts/`.

## File / module conventions

- `scripts/` = pure capability functions, callable as `python -m scripts.X`
  and importable as tools.
- `agents/clinic_assitant.py` = single agent definition + one-shot CLI.
- `agents/chat.py` = REPL loop reusing one thread.
- `api/main.py` = thin FastAPI wrapper around the same functions + agent.
- Don't introduce a parallel `core/` indirection layer just to wrap one Azure
  client — inline the construction at the call site.
