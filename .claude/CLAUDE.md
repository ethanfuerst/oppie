# oppie — Project Conventions

## Tech stack

| Category | Choice | Notes |
|----------|--------|-------|
| CLI framework | Click | User preference from prior project experience |
| CLI output | Rich | Styled output (spinners, checkmarks, tables) |
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

- `httpx` is **not** a core dep — it lives in `[project.optional-dependencies]`.
- Extras: `linear` (httpx), `openai` (httpx), `anthropic` (httpx), `all` (aggregates all three). No `tui` extra yet — bare `oppie` still prints a forward-looking `pip install oppie[tui]` hint that will be wired up in ETH-369 (0.2.0).
- Missing-extra error template (CLI messages and `ImportError` strings alike): `<Feature> requires the '<name>' extra.` + `Install with: pip install 'oppie[<name>]'`. In `console.print` calls the brackets must be Rich-escaped (`\[name]`); in plain `ImportError` strings they must not.
- Per-backend hint routing: `openai_compatible.py` hints `oppie[openai]`; `anthropic.py` hints `oppie[anthropic]`; `LinearProvider` hints `oppie[linear]`. `oppie/health/checks.py` has `_LLM_EXTRA_BY_BACKEND` + `_llm_install_hint()` that dispatches on `config.llm.backend.value`. `oppie/cli/commands/init.py` checks the extra for the backend the user picks (inside `_prompt_llm_config`) and errors with a backend-specific hint.
- LLM provider modules (`openai_compatible.py`, `anthropic.py`, `_sse.py`) and `LinearProvider` use lazy imports: `try: import httpx / except ImportError: httpx = None` with `from __future__ import annotations` for deferred type evaluation. Provider constructors raise `ImportError` with install hint if httpx is missing. The factory (`create_llm_provider()`) wraps this into `LLMNotConfiguredError`.
- CI jobs that need httpx use `uv sync --frozen --all-extras`. The `core-import-check` CI job validates that `import oppie` works without extras.

## Commit style

Conventional commits enforced in CI. Format: `type: description`

Allowed types: `feat`, `fix`, `ci`, `chore`, `docs`, `refactor`, `test`

## Release & versioning

- `.github/workflows/release.yml` has two jobs: `release` (commitizen `cz bump` + tag + GitHub release) and `publish-pypi` (OIDC trusted publishing, `environment: pypi`). Triggers: push to `main` (auto-bump from commit history) and `workflow_dispatch` with explicit `bump: patch|minor|major|auto`.
- Version is sourced from `pyproject.toml`. `[tool.commitizen].version_files` keeps `oppie/__init__.py:^__version__` in lockstep. Tests that care about the version reference `oppie.__version__`, not literal strings (see `tests/instance/test_marker.py`).
- `main` has no branch protection (the release job pushes the bump commit using the default `GITHUB_TOKEN`). Runbook for one-time GitHub/PyPI setup lives in `next_steps.md`.

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
- `oppie/health/` — Instance health checking and data repair package. `checks.py` has `CheckStatus`, `CheckResult` dataclasses and 10 health check functions (`check_config`, `check_state_cache`, `check_tickets`, `check_outbox`, `check_artifacts`, `check_run_log`, `check_provider_connectivity`, `check_llm_connectivity`, `check_extras`, `check_missing_deps`) plus `run_all_checks()` orchestrator. `repair.py` has `RepairIssue`, `RepairResult` dataclasses, 5 scan functions (`scan_run_log`, `scan_tickets`, `scan_plan_index`, `scan_sqlite`, `scan_permissions`), 3 repair functions (`repair_run_log`, `repair_ticket_versions`, `repair_plan_index`) using atomic writes, plus `scan_all()` and `apply_repairs()` orchestrators. `__init__.py` re-exports all public symbols. Used by both CLI `health` and `repair` commands, designed for TUI reuse.
- `oppie/providers/` — Storage backends. `base.py` defines `TicketProvider` ABC (with `home` property, `read_ticket`, `update_ticket`, `list_tickets`, `search_tickets` (default in-memory, overridable), `upsert_ticket`, `capabilities`, and concrete `validate_operations` which checks both field support and value constraints), `ExternalProvider` (adds `sync`/`apply`/`test_connection`/`flush_outbox` plus default no-op `close()`), and the `ProviderError` hierarchy: `ProviderError` root with `ProviderAuthError`, `ProviderRateLimitError(retry_after)`, `ProviderNetworkError`, `ProviderAPIError`. `LinearAPIError` re-parents on `ProviderAPIError`; `LinearAuthError`/`LinearRateLimitError` use multiple inheritance to keep `LinearAPIError` as a base (preserves in-loop swallowing in `LinearProvider.sync()`/`apply()`). `LinearProvider._graphql()` wraps all `httpx.HTTPError` (including `HTTPStatusError`) into `ProviderNetworkError` at both call sites. CLI (`sync.py`) imports only from `oppie.providers.base` — no `httpx`, no Linear-specific exception imports. `factory.py` has `create_external_provider(config, home, cache) -> ExternalProvider` with lazy concrete-provider imports; raises `ValueError` for non-external types. CLI (`sync.py`) constructs external providers via the factory rather than importing `LinearProvider` directly. `ProviderCapabilities` includes `field_constraints` dict mapping field names to allowed values (or `None` for free-form). Each provider is a package: `local/` has `provider.py` (`LocalProvider` with JSON+SQLite and `setup()` classmethod) and `__init__.py` re-exports. `linear/` has `config.py` (`LinearProviderConfig` with `to_dict()`), `provider.py` (`LinearProvider` with `setup()` classmethod for interactive init, `test_connection()` via `_graphql('{ viewer { id } }')`), `discovery.py` (standalone GraphQL functions for listing teams/projects during init), and `__init__.py` re-exports.
- `oppie/logging.py` — `configure_logging(debug, home)` sets up stdlib logging. File output to `{home}/logs/oppie-{timestamp}.log` when an initialized instance exists, stderr fallback otherwise. `OPPIE_LOG_LEVEL` env var overrides `--debug`.
- `oppie/prompts/` — Layered prompt assembly. `formatting.py` has `load_context()`, `format_tickets_for_llm()`, `format_context_for_llm()`, `format_past_plans()`. `plan.py` and `ask.py` define mode-specific base prompts (`PLAN_BASE_PROMPT`, `ASK_BASE_PROMPT`). `builder.py` has `PromptMode`, `SystemPromptPart`, `build_system_prompt()` (3-layer assembly: base + context + dynamic), `flatten_system_prompt()`.
- `oppie/intent.py` — Intent classification. `Intent` enum (`QUESTION`, `INSTRUCTION`, `APPLY`), `classify_intent()` (async, LLM-only — no local heuristics). Raises `IntentClassificationError` when the LLM call fails, returns no `intent` field, or returns an invalid label. `handle_prompt` catches this and prints the spec's "Could not determine intent" clarification message (exit 0). LLM config required for prompt command.
- `oppie/sync.py` — `auto_sync(provider, no_sync=False)` runs sync for `ExternalProvider`s, no-op for local. Returns `AutoSyncResult` with synced/ticket_count/duration/error.
- `oppie/tools/` — LLM-callable tool definitions. `base.py` defines `Tool`, `ToolContext`, `ToolResult`. `tickets.py` has `SEARCH_TICKETS_TOOL` and `GET_TICKET_TOOL`. `operations.py` has `PROPOSE_OPERATION_TOOL` (plan mode only, validates against `ProviderCapabilities`).
- `oppie/events.py` — Streaming event types. All events are `@dataclass(slots=True)`. `EngineEvent` is a union type alias. Engine-emitted: `StepStartEvent`, `ThinkingEvent`, `TextDeltaEvent`, `ToolCallEvent`, `PlanOperationEvent`, `StatsEvent` (has `step_durations: dict[str, float]` populated per step by `run_engine`). Caller-emitted: `SyncStartEvent`/`SyncDoneEvent` (CLI/TUI layer). Domain result events: `PlanResultEvent(plan)`, `AskResultEvent(result)`. Internal: `_StepDoneEvent` (usage/turns sentinel, intercepted by `run_engine()`, never yielded to callers).
- `oppie/engine.py` — Multi-turn agent loop. `EngineMode` (`ASK`/`PLAN`), `EngineStep` (defines tools, tool_choice, max_turns per step), `EngineResult`. Mode-specific step sequences: plan = research -> propose (forced `propose_operation`) -> summary; ask = research -> answer. `run_engine()` is an `AsyncGenerator[EngineEvent, None]` that yields events incrementally. Text-only steps (summary/answer) use `llm.stream()` for `TextDeltaEvent` chunks; tool steps use `llm.generate()`. `collect_engine_result()` consumes the generator and returns `(EngineResult, list[EngineEvent])`. `_run_step()` is also a generator, yields `_StepDoneEvent` sentinel for usage tracking.
- `oppie/ask/` — Ask engine package. `engine.py` has `generate_ask()` — an `AsyncGenerator[EngineEvent, None]` that re-yields engine events and yields `AskResultEvent` at the end. Requires LLM backend. Saves ask artifacts and run log entries. `__init__.py` re-exports `generate_ask`.
- `oppie/cli/` — Click CLI package. `__init__.py` uses custom `PromptOrCommand` group class to support bare `oppie "<prompt>"` entry point — unrecognized first positional arg is rewritten by injecting the hidden `handle_prompt` subcommand name before it, so trailing options (e.g. `--force`) bind to that subcommand. Has `--home`, `--debug`, `--no-sync` flags at the root. Bare `oppie` (no subcommand) prints help + a TUI install hint (`pip install oppie[tui]`); the TUI itself is ETH-369. `commands/` has one module per command area (`init.py`, `config_cmd.py`, `context.py`, `prompt.py`, `amend.py`, `apply.py`, `show.py`, `history.py`, `state.py`, `health.py`, `repair.py`, `sync.py`). `render.py` defines `RenderMode` (ASK/PLAN), `EventRenderer` (class-based, per-event handlers like `on_thinking`/`on_text_delta`/`on_tool_call`/`on_plan_operation`/`on_stats` — overridable for TUI subclassing) with `async def consume(events)` that dispatches each `EngineEvent` and stores final domain results on `renderer.ask_result` / `renderer.plan`. `render_sync(renderer, home, config, *, no_sync)` is a `@contextmanager` that wraps `setup_provider` and feeds `SyncStartEvent`/`SyncDoneEvent` to the renderer (calls `setup_provider` with `print_sync_success=False` so the renderer owns the success line). `sync.py` is the user-facing `oppie sync` command (distinct from `oppie.sync`): flushes outbox then pulls from Linear, supports `--full` (passes `checkpoint=''`) and `--no-flush`. Exit codes: 0 ok, 1 missing extra, 2 auth, 3 rate limit, 4 network, 5 other LinearAPIError. Deferred imports of `httpx`/`LinearProvider` after extras check. Escape Rich markup brackets in install hints (e.g., `'oppie\[linear]'`). `apply.py` has the `apply` command with extracted helper functions for each interaction state (error handling, drift resolution, operation display, results). `prompt.py` routes by intent: QUESTION → `_handle_ask()`, INSTRUCTION → `_handle_plan()`, APPLY → `_handle_apply()` (imports `run_apply` from `apply.py`). `_handle_ask`/`_handle_plan` use `EventRenderer` + `render_sync` to stream events live (Thinking spinner, text deltas, tool-call indicators, plan ops as they arrive, stats footer). `handle_prompt` accepts a real `--force` flag (apply only); effective force is `flag_force or 'force' in prompt_lower or '--force' in prompt_lower` so the in-prompt UX still works. `show.py` displays plan or apply details by ID (tries plan first, then scans apply artifacts). `history.py` shows run log entries with `--limit`. `state.py` is a Click group with `show` subcommand for instance state summary (file counts, no deserialization). `console.py` has shared Rich output helpers (`success`, `warn`, `error`, `info`). `extras.py` detects installed optional extras at runtime. `provider_setup.py` exposes `setup_provider(home, config, *, no_sync=False, print_sync_success=True)` as a `@contextmanager` yielding `(provider, AutoSyncResult)`. `print_sync_success=False` suppresses only the success line (cached/error lines still print) so `render_sync` can narrate sync via events without double-printing. Dispatches on `config.provider.provider_type`: local builds `LocalProvider`; linear checks the `linear` extra (exits 1 with install hint if missing), constructs a `LocalProvider` cache, and delegates to `create_external_provider(config, home, cache=cache)`. An internal `ExitStack` closes both provider and cache on exit. Falls back to the cache `LocalProvider` on `ValueError` from the factory (e.g., missing API key). Runs `auto_sync()` and prints status (`✓ Synced`/`⚠ Sync failed`/`● Using cached data`). Used by `prompt.py`, `apply.py`, `amend.py` via `with setup_provider(...)` blocks.
- `oppie/config.py` — YAML config loading/saving, `OppieConfig` and `InstanceType` (local/remote). `OppieConfig.llm` is a required `LLMConfig` field (no default). `save_oppie_config()` and `save_provider_credentials()` use atomic writes.
- `oppie/instance.py` — Instance initialization and discovery. Creates the directory tree under a home dir with a `.oppie-marker` file.
- `oppie/artifacts.py` — `ArtifactStore` for saving/reading/listing JSON artifacts (ask, plan, apply, report, context) under `artifacts/`.
- `oppie/run_log.py` — `RunLog` for append-only JSONL run logging under `logs/runs.jsonl`.
- `oppie/plan/` — Plan orchestration package. `engine.py` contains module-level functions for the full plan lifecycle: `generate_plan()` (async generator yielding `EngineEvent`s, has `save` kwarg defaulting to `True`), `_consume_plan_generator()` (consumes generator, returns `Plan`), `amend_plan()` (async, uses `_consume_plan_generator()`), `check_apply()`, `execute_apply()`, `load_plan()`. Also contains `PreApplyCheck` dataclass, preflight validation, drift detection, and plan apply execution. Requires LLM backend — no fallback paths. `__init__.py` re-exports all public functions and `PreApplyCheck`.
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

- `oppie/llm/`, `run_engine()`, `generate_plan()`, `generate_ask()` are async generators. `amend_plan()` is async (consumes generator internally). All `LLMProvider` methods are async. `check_apply()`/`execute_apply()` and drift detection are synchronous.
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
- CLI command hints in user-facing messages use the full form: `oppie <command>`.
