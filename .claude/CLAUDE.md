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

## Optional dependencies (extras)

- `httpx` and `textual` are **not** core deps — they live in `[project.optional-dependencies]`.
- Extras: `llm` (httpx), `tui` (textual), `all` (both).
- LLM provider modules (`openai_compatible.py`, `anthropic.py`, `_sse.py`) use lazy imports: `try: import httpx / except ImportError: httpx = None` with `from __future__ import annotations` for deferred type evaluation. Provider constructors raise `ImportError` with install hint if httpx is missing. The factory (`create_llm_provider()`) wraps this into `LLMNotConfiguredError`.
- CI jobs that need httpx/textual use `uv sync --frozen --all-extras`. The `core-import-check` CI job validates that `import oppie` works without extras.

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
- `oppie/artifacts.py` — `ArtifactStore` for saving/reading/listing markdown artifacts (ask, plan, apply, report, context) under `artifacts/`.
- `oppie/run_log.py` — `RunLog` for append-only JSONL run logging under `logs/runs.jsonl`.
- `oppie/plan/` — Plan generation package. `engine.py` has async entry points (`generate_plan`, `amend_plan`). `fallback.py` has keyword matching. `preflight.py` validates operations. `persistence.py` handles save/load and JSONL index. `schema.py` has `PLAN_RESPONSE_SCHEMA`, `load_context`, `find_similar_plans`. `__init__.py` re-exports all public names. Accepts `home: Path` + `config: OppieConfig | None` (not `Instance`) to avoid circular imports.
- `oppie/prompts/plan.py` — LLM prompt construction for plan generation. `build_plan_prompt()` returns OpenAI-format messages.
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
  artifacts/plans/.plan-index.jsonl  # JSONL index for plan keyword search
  context/{vision,roadmap,metrics,prioritization}.md  # Optional context docs
```

## Async conventions

- `oppie/llm/` and `oppie/plan_engine.py` are async. All `LLMProvider` methods are async.
- Textual (TUI) callers can `await` directly since Textual runs on asyncio.
- Non-TUI callers (CLI commands without TUI) wrap with `asyncio.run()`.
- Both LLM providers implement async context manager protocol (`async with provider:`) for proper httpx client cleanup.

## Code style

- Single quotes for strings.
- f-strings for interpolation.
- snake_case for variables/functions, PascalCase for classes, UPPER_SNAKE_CASE for constants.
- Type hints on all public function signatures.
- Imports at top of file (no in-method imports except in tests when needed).
