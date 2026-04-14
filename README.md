# oppie

A project-management operations CLI with a plan/apply workflow. Propose changes
from natural-language prompts, review them as structured operations, then apply.

## Install

oppie is distributed on PyPI. Core install:

    pip install oppie

Optional features ship as extras:

| Extra            | Enables                                       |
|------------------|-----------------------------------------------|
| `oppie[llm]`     | LLM backends (OpenAI-compatible and Anthropic) |
| `oppie[linear]`  | Linear ticket provider                         |
| `oppie[tui]`     | Textual TUI (coming soon)                      |
| `oppie[all]`     | All of the above                               |

An LLM backend is required for normal use. Most users want:

    pip install 'oppie[llm]'

Add `linear` if you sync tickets from Linear:

    pip install 'oppie[llm,linear]'

## Quickstart

    # 1. Initialize an instance in the current directory
    oppie init

    # 2. (optional) View or edit config
    oppie config show

    # 3. Ask a question or request a plan
    oppie "what's the status of the migration work?"

`oppie init` walks through picking an instance type (local or Linear-backed),
configuring an LLM backend, and optionally seeding context docs.

## Usage example

End-to-end: ask for a plan, review it, then apply it.

    $ oppie "update the priority of the auth-rewrite ticket to high"
    ● Classifying intent…
    ● Generating plan…
    Plan plan-01HX… (1 operation)
      - update ticket TKT-42: priority = high

    $ oppie apply plan-01HX…
    ✓ Applied 1 operation

Plans are content-addressed and stored under the instance home; re-running with
the same prompt produces the same plan id when nothing has changed.

## CLI flag reference

Root flags (apply to every subcommand):

| Flag              | Description                                          |
|-------------------|------------------------------------------------------|
| `--home PATH`     | Override instance home auto-detection                |
| `--debug`         | Enable debug logging (also via `OPPIE_LOG_LEVEL`)    |
| `--no-sync`       | Skip auto-sync; use cached ticket data               |

Conversational CLI (`oppie "<prompt>"`):

| Flag      | Description                                                     |
|-----------|-----------------------------------------------------------------|
| `--force` | Skip drift prompts when the intent resolves to an apply         |

Selected subcommand flags:

| Command                  | Flag           | Description                           |
|--------------------------|----------------|---------------------------------------|
| `oppie apply <plan_id>`  | `--force`      | Overwrite drift without prompting     |
| `oppie sync`             | `--full`       | Ignore checkpoint, re-sync everything |
| `oppie sync`             | `--no-flush`   | Skip flushing the outbound queue      |

Run `oppie --help` or `oppie <command> --help` for the full list.

## Exit codes

General contract for all commands:

| Code | Meaning  |
|------|----------|
| `0`  | Success  |
| `1`  | Error    |

`oppie sync` returns a more granular code so CI scripts can distinguish
retryable failures:

| Code | Meaning              |
|------|----------------------|
| `0`  | Success              |
| `1`  | Generic error        |
| `2`  | Auth error           |
| `3`  | Rate limited         |
| `4`  | Network error        |
| `5`  | Provider API error   |

## Development

    # Install dev deps (all extras)
    uv sync --all-extras

    # Pre-commit
    uv run pre-commit run --all-files

    # Tests
    uv run pytest

    # Lint and format
    uv run ruff check .
    uv run ruff format .
