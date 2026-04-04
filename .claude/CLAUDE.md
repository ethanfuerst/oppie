# oppie — Project Conventions

## Tech stack

| Category | Choice | Notes |
|----------|--------|-------|
| CLI framework | Click | User preference from prior project experience |
| CLI output | Rich | Styled output (spinners, checkmarks, tables) |
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
- Extras: `llm` (httpx), `linear` (httpx), `tui` (textual), `all` (all three).
- LLM provider modules (`openai_compatible.py`, `anthropic.py`, `_sse.py`) and `LinearProvider` use lazy imports: `try: import httpx / except ImportError: httpx = None` with `from __future__ import annotations` for deferred type evaluation. Provider constructors raise `ImportError` with install hint if httpx is missing. The factory (`create_llm_provider()`) wraps this into `LLMNotConfiguredError`.
- CI jobs that need httpx/textual use `uv sync --frozen --all-extras`. The `core-import-check` CI job validates that `import oppie` works without extras.

## Commit style

Conventional commits enforced in CI. Format: `type: description`

Allowed types: `feat`, `fix`, `ci`, `chore`, `docs`, `refactor`, `test`

## Testing rules

- Use pytest. Run with `uv run pytest`.
- 100% coverage on touched files.
- Use plain `test_*` functions, not `Test*` classes.
- Organize test files by area in subdirectories (e.g., `tests/models/`, `tests/providers/`, `tests/drift/`).
- Each test subdirectory has `__init__.py` and optionally `conftest.py` for directory-scoped helpers/fixtures.
- Root `tests/conftest.py` has cross-cutting fixtures (e.g., `home`, `provider`). `tests/helpers.py` has shared helpers (`make_ticket`, `write_ticket`, `setup_instance`).
- `tests/providers/local/conftest.py` has its own `make_ticket` (different signature from `tests/helpers.make_ticket`) and an autouse `_close_provider` fixture for `LocalProvider` cleanup. `tests/providers/linear/conftest.py` follows the same pattern with LINEAR-sourced tickets.
- `tests/cli/conftest.py` has `setup_cli_instance()` which creates a full instance with `.oppie-marker` and config — required for CLI integration tests that go through `Instance.detect()`. Also has `make_and_save_plan()` helper.

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
- `oppie/llm/__init__.py` exports types (`LLMProvider`, `LLMResponse`, `TokenUsage`, `StreamResult`, `ToolCallRequest`, `ToolCallResult`, `LLMNotConfiguredError`) and `create_llm_provider()`. Import from submodules for internal use (e.g., `from oppie.llm.base import TokenUsage`).
- `oppie/prompts/__init__.py` exports formatting helpers (`load_context`, `format_tickets_for_llm`, `format_context_for_llm`, `format_past_plans`) and builder types (`PromptMode`, `SystemPromptPart`, `build_system_prompt`, `flatten_system_prompt`).
- `oppie/tools/__init__.py` exports `Tool`, `ToolContext`, `ToolResult`.
- `oppie/ask/__init__.py` exports `generate_ask`.

## Project structure

- `oppie/models/` — Pure data models (Ticket, Plan, Operation, Apply, Drift, etc.). Each in its own file. No orchestration logic or I/O. `Plan.plan_id` is auto-computed in `__post_init__` from operations. `Plan.checked` tracks whether `check_apply()` has validated it (required before `execute_apply()`). `Plan.save(home)` handles atomic JSON persistence and index updates. `FieldDrift` has optional `updated_at`/`updated_by` fields populated by `_check_drift()` for display in drift resolution prompts.
- `oppie/providers/` — Storage backends. `base.py` defines `TicketProvider` ABC (with `home` property, `read_ticket`, `update_ticket`, `list_tickets`, `search_tickets` (default in-memory, overridable), `upsert_ticket`, `capabilities`, and concrete `validate_operations` which checks both field support and value constraints) and `ExternalProvider` (adds `sync`/`apply`). `ProviderCapabilities` includes `field_constraints` dict mapping field names to allowed values (or `None` for free-form). Each provider is a package: `local/` has `provider.py` (`LocalProvider` with JSON+SQLite and `setup()` classmethod) and `__init__.py` re-exports. `linear/` has `config.py` (`LinearProviderConfig` with `to_dict()`), `provider.py` (`LinearProvider` with `setup()` classmethod for interactive init), `discovery.py` (standalone GraphQL functions for listing teams/projects during init), and `__init__.py` re-exports.
- `oppie/logging.py` — `configure_logging(debug, home)` sets up stdlib logging. File output to `{home}/logs/oppie-{timestamp}.log` when an initialized instance exists, stderr fallback otherwise. `OPPIE_LOG_LEVEL` env var overrides `--debug`.
- `oppie/prompts/` — Layered prompt assembly. `formatting.py` has `load_context()`, `format_tickets_for_llm()`, `format_context_for_llm()`, `format_past_plans()`. `plan.py` and `ask.py` define mode-specific base prompts (`PLAN_BASE_PROMPT`, `ASK_BASE_PROMPT`). `builder.py` has `PromptMode`, `SystemPromptPart`, `build_system_prompt()` (3-layer assembly: base + context + dynamic), `flatten_system_prompt()`.
- `oppie/intent.py` — Intent classification. `Intent` enum (`QUESTION`, `INSTRUCTION`, `AMBIGUOUS`), `classify_intent()` (local heuristics), `classify_intent_llm()` (async, LLM-based with heuristic fallback). Config field `intent_classification` (`local`/`llm`) controls strategy.
- `oppie/sync.py` — `auto_sync(provider, no_sync=False)` runs sync for `ExternalProvider`s, no-op for local. Returns `AutoSyncResult` with synced/ticket_count/duration/error.
- `oppie/tools/` — LLM-callable tool definitions. `base.py` defines `Tool`, `ToolContext`, `ToolResult`. `tickets.py` has `SEARCH_TICKETS_TOOL` and `GET_TICKET_TOOL`. `operations.py` has `PROPOSE_OPERATION_TOOL` (plan mode only, validates against `ProviderCapabilities`).
- `oppie/engine.py` — Multi-turn agent loop. `EngineMode` (`ASK`/`PLAN`), `EngineStep` (defines tools, tool_choice, max_turns per step), `EngineResult`. Mode-specific step sequences: plan = research -> propose (forced `propose_operation`) -> summary; ask = research -> answer. `run_engine()` is the main entry point, called by both `generate_plan` and `generate_ask`.
- `oppie/ask/` — Ask engine package. `engine.py` has `generate_ask()` (async) — uses `run_engine()` with ask-mode steps, falls back to keyword-based answers when no LLM configured. Saves ask artifacts and run log entries. `__init__.py` re-exports `generate_ask`.
- `oppie/cli/` — Click CLI package. `__init__.py` uses custom `PromptOrCommand` group class to support bare `oppie "<prompt>"` entry point — unrecognized first positional arg is treated as a prompt. Has `--home`, `--debug`, `--no-sync` flags. `commands/` has one module per command area (`init.py`, `config_cmd.py`, `context.py`, `prompt.py`, `amend.py`, `apply.py`). `apply.py` has the `apply` command with extracted helper functions for each interaction state (error handling, drift resolution, operation display, results). `console.py` has shared Rich output helpers (`success`, `warn`, `error`, `info`). `extras.py` detects installed optional extras at runtime.
- `oppie/config.py` — YAML config loading/saving, `OppieConfig` and `InstanceType` (local/remote), `IntentClassification` enum. `save_oppie_config()` and `save_provider_credentials()` use atomic writes.
- `oppie/instance.py` — Instance initialization and discovery. Creates the directory tree under a home dir with a `.oppie-marker` file.
- `oppie/artifacts.py` — `ArtifactStore` for saving/reading/listing JSON artifacts (ask, plan, apply, report, context) under `artifacts/`.
- `oppie/run_log.py` — `RunLog` for append-only JSONL run logging under `logs/runs.jsonl`.
- `oppie/plan/` — Plan orchestration package. `engine.py` contains module-level functions for the full plan lifecycle: `generate_plan()` (async, uses `run_engine()` with plan-mode steps, has `save` kwarg defaulting to `True`), `amend_plan()` (async), `check_apply()`, `execute_apply()`, `load_plan()`. Also contains `PreApplyCheck` dataclass, fallback keyword-based plan generation, preflight validation, drift detection, and plan apply execution. `__init__.py` re-exports all public functions and `PreApplyCheck`.
- `oppie/llm/` — LLM provider abstraction. `base.py` defines the `LLMProvider` ABC, `TokenUsage`, `LLMResponse`, `StreamResult`, `ToolCallRequest`, `ToolCallResult` dataclasses, and `LLMNotConfiguredError`. `LLMProvider.generate()` accepts `tools` (list of tool schemas) and `tool_choice` (None/`'any'`/`{'name': '...'}`) for tool-calling. `openai_compatible.py` and `anthropic.py` are the two backends — both handle tool-calling and map to their respective API formats. `_sse.py` is a shared SSE parser. `__init__.py` exports types and `create_llm_provider()` factory.
- `oppie/session.py` — `Session` for per-session state (`state/session-{uuid}.json`). Tracks active plan, recent run IDs, last command timestamp. Supports multiple concurrent sessions via UUID-keyed files.

### Instance directory layout

```
<home>/
  .oppie-marker        # JSON marker with version + instance type
  config/              # YAML config
  state/snapshots/     # State snapshots
  state/linear/        # Linear provider state (checkpoint, outbox, lock)
  tickets/             # JSON ticket files (local provider)
  artifacts/{ask,plans,applies,reports,context}/
  state/session-*.json # Per-session state files (UUID-keyed)
  logs/runs.jsonl      # Append-only run log
  logs/oppie-*.log     # Per-invocation debug log files (created by --debug)
  artifacts/plans/.plan-index.jsonl  # JSONL index for plan keyword search
  context/{vision,roadmap,metrics,prioritization}.md  # Optional context docs
```

## Async conventions

- `oppie/llm/` and `oppie.plan.generate_plan()`/`amend_plan()` are async. All `LLMProvider` methods are async. `oppie.plan.check_apply()`/`execute_apply()` and drift detection are synchronous.
- Textual (TUI) callers can `await` directly since Textual runs on asyncio.
- Non-TUI callers (CLI commands without TUI) wrap with `asyncio.run()`.
- Both LLM providers implement async context manager protocol (`async with provider:`) for proper httpx client cleanup.

## Dataclass conventions

- Value-object dataclasses use `@dataclass(slots=True)` for memory efficiency and attribute-access speed.
- Dataclasses mutated after `__init__` do **not** use `slots=True`: `Plan`, `Ticket`, `SessionData`.
- When adding a new dataclass, use `slots=True` unless the class needs post-init mutation (e.g., `setattr`, field reassignment outside `__init__`).

## Logging conventions

- Every module that logs uses `logger = logging.getLogger(__name__)` at module level.
- `configure_logging()` in `oppie/logging.py` is called once from the CLI callback. It checks whether `{home}/logs/` exists before writing file logs — avoids creating directories before `oppie init`.
- Use `logger.info()` for high-level operations (plan generation, apply execution). Use `logger.debug()` for internal details (ticket counts, cache refreshes, GraphQL calls). Use `logger.warning()` for recoverable issues (corrupt session files).
- Log format: `%(asctime)s %(name)s %(levelname)s %(message)s`. Use `%s`-style formatting (not f-strings) in log calls for lazy evaluation.

## Code style

- Single quotes for strings.
- f-strings for interpolation.
- snake_case for variables/functions, PascalCase for classes, UPPER_SNAKE_CASE for constants.
- Type hints on all public function signatures.
- Imports at top of file (no in-method imports except in tests when needed).
- Provider `.setup()` classmethods use in-method imports (Click, discovery) since they're only called during `oppie init`.
- CLI command module `config_cmd.py` (not `config.py`) avoids shadowing `oppie.config`.
