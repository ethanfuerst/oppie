# oppie — Project Conventions

## Tech stack

| Category | Choice | Notes |
|----------|--------|-------|
| CLI framework | Click | User preference from prior project experience |
| TUI library | Textual | Full TUI framework with widgets, layout, async |
| Async framework | asyncio | Stdlib, works with Textual natively |
| HTTP client | httpx | Async + sync hybrid, streaming support, HTTP/2 |
| LLM client | httpx + custom adapter | Minimal LLMProvider interface using httpx |
| Hashing | hashlib (stdlib) | SHA-256 for plan content hashing |
| Testing | pytest | Modern standard, clean fixtures |
| Config parsing | PyYAML | YAML config format |
| Database | sqlite3 (stdlib) | For indexes/checkpoints only; tickets stored as JSON |
| Python version | 3.12+ | Minimum supported version |
| Package manager | uv | Fast, modern, good lockfile support |

## Commit style

Conventional commits enforced in CI. Format: `type: description`

Allowed types: `feat`, `fix`, `ci`, `chore`, `docs`, `refactor`, `test`

## Testing rules

- Use pytest. Run with `uv run pytest`.
- 100% coverage on touched files.
- Use plain `test_*` functions, not `Test*` classes.
- Organize test files by area (e.g., `tests/models/`, `tests/providers/`).
- Shared fixtures go in `tests/conftest.py`.

## Development commands

- Lint: `uv run ruff check .`
- Format: `uv run ruff format .`
- Type check: `uv run mypy oppie/`
- Test: `uv run pytest`
- Pre-commit: `uv run pre-commit run --all-files`
- Before finishing: run `uv run ruff check .` and `uv run ruff format --check .` in addition to pre-commit to catch lint errors (e.g., unused variables) that may only surface during `git commit`.

## Import conventions

- Import model classes from their submodule, not from `oppie.models` (e.g., `from oppie.models.ticket import Ticket`, not `from oppie.models import Ticket`).
- `oppie/models/__init__.py` only exports `SCHEMA_VERSION` and type aliases (`RunId`, `PlanId`, `SessionId`).
- `oppie/llm/__init__.py` exports types (`LLMProvider`, `LLMResponse`, `TokenUsage`, `StreamResult`, `LLMNotConfiguredError`) and `create_llm_provider()`. Import from submodules for internal use (e.g., `from oppie.llm.base import TokenUsage`).

## Project structure

- `oppie/models/` — Core data models (Ticket, Plan, Operation, Apply, etc.). Each in its own file.
- `oppie/providers/` — Storage backends. `base.py` defines the `TicketProvider` ABC; `local.py` implements JSON-file-per-ticket storage with SQLite indexing.
- `oppie/config.py` — YAML config loading, `OppieConfig` and `InstanceType` (local/remote).
- `oppie/instance.py` — Instance initialization and discovery. Creates the directory tree under a home dir with a `.oppie-marker` file.
- `oppie/artifacts.py` — `ArtifactStore` for saving/reading markdown artifacts (ask, plan, apply, report, context) under `artifacts/`.
- `oppie/run_log.py` — `RunLog` for append-only JSONL run logging under `logs/runs.jsonl`.
- `oppie/llm/` — LLM provider abstraction. `base.py` defines the `LLMProvider` ABC, `TokenUsage`, `LLMResponse`, `StreamResult` dataclasses, and `LLMNotConfiguredError`. `openai_compatible.py` and `anthropic.py` are the two backends. `_sse.py` is a shared SSE parser. `__init__.py` exports types and `create_llm_provider()` factory.
- `oppie/session.py` — `Session` for per-session state (`state/session-{uuid}.json`). Tracks active plan, recent run IDs, last command timestamp. Supports multiple concurrent sessions via UUID-keyed files.

### Instance directory layout

```
<home>/
  .oppie-marker        # JSON marker with version + instance type
  config/              # YAML config
  state/snapshots/     # State snapshots
  tickets/             # JSON ticket files (local provider)
  artifacts/{ask,plans,applies,reports,context}/
  state/session-*.json # Per-session state files (UUID-keyed)
  logs/runs.jsonl      # Append-only run log
```

## Async conventions

- `oppie/llm/` is the first async module in the codebase. All `LLMProvider` methods are async.
- Textual (TUI) callers can `await` directly since Textual runs on asyncio.
- Non-TUI callers (CLI commands without TUI) wrap with `asyncio.run()`.
- Both LLM providers implement async context manager protocol (`async with provider:`) for proper httpx client cleanup.

## Code style

- Single quotes for strings.
- f-strings for interpolation.
- snake_case for variables/functions, PascalCase for classes, UPPER_SNAKE_CASE for constants.
- Type hints on all public function signatures.
- Imports at top of file (no in-method imports except in tests when needed).
