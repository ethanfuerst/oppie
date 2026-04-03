import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from oppie.artifacts import ArtifactStore, ArtifactType
from oppie.config import OppieConfig
from oppie.llm import LLMNotConfiguredError, create_llm_provider
from oppie.llm.base import TokenUsage
from oppie.models.ticket import Ticket
from oppie.prompt.helpers import (
    format_context_for_llm,
    format_tickets_for_llm,
    load_context,
)
from oppie.providers.base import TicketProvider
from oppie.run_log import RunLog, RunLogEntry, generate_run_id

logger = logging.getLogger(__name__)

_ASK_SYSTEM_PROMPT = """\
You are oppie, a project management assistant. Answer the user's question \
based on the ticket data and context provided. Be concise and reference \
ticket IDs as evidence. If data is insufficient, say so.\
"""

# Keywords for fallback filtering
_STATUS_KEYWORDS: dict[str, str] = {
    'blocked': 'blocked',
    'open': 'open',
    'closed': 'done',
    'done': 'done',
    'in progress': 'in_progress',
    'in_progress': 'in_progress',
    'todo': 'todo',
}

_PRIORITY_KEYWORDS: dict[str, str] = {
    'urgent': 'urgent',
    'high': 'high',
    'medium': 'medium',
    'low': 'low',
}


@dataclass(slots=True)
class AskResult:
    """Result of an ask operation."""

    answer: str
    artifact_path: Path | None
    run_id: str
    duration: float
    usage: TokenUsage | None


async def generate_ask(
    provider: TicketProvider,
    config: OppieConfig | None,
    question: str,
) -> AskResult:
    """Answer a question about tickets.

    Pipeline:
    1. Load tickets and context.
    2. Try LLM-powered answer; fall back to keyword-based template.
    3. Save ask artifact and run log entry.
    """
    logger.info('Generating ask for question: %r', question)
    home = provider.home
    start = time.monotonic()

    tickets = provider.list_tickets()
    context = load_context(home)

    try:
        llm_config = config.llm if config else None
        llm = create_llm_provider(llm_config)
    except LLMNotConfiguredError:
        logger.debug('Using fallback ask (no LLM configured)')
        answer = _generate_fallback(tickets, question)
        duration = time.monotonic() - start
        run_id = generate_run_id()
        artifact_path = _save_ask_artifact(home, question, answer, run_id)
        _append_run_log(home, run_id, duration, artifact_path, None)
        return AskResult(
            answer=answer,
            artifact_path=artifact_path,
            run_id=run_id,
            duration=duration,
            usage=None,
        )

    messages = _build_ask_prompt(question, context, tickets)

    async with llm:
        response = await llm.generate(
            messages=messages,
            max_tokens=llm_config.max_tokens if llm_config else 2000,
            temperature=llm_config.temperature if llm_config else 0.7,
        )

    duration = time.monotonic() - start
    run_id = generate_run_id()
    artifact_path = _save_ask_artifact(home, question, response.text, run_id)
    _append_run_log(home, run_id, duration, artifact_path, response.usage)

    return AskResult(
        answer=response.text,
        artifact_path=artifact_path,
        run_id=run_id,
        duration=duration,
        usage=response.usage,
    )


def _build_ask_prompt(
    question: str,
    context: dict[str, str],
    tickets: list[Ticket],
) -> list[dict]:
    """Build OpenAI-format messages for ask."""
    context_section = format_context_for_llm(context)
    context_block = f'\n# Context\n{context_section}\n' if context_section else ''

    user_content = f"""\
{context_block}
# Current tickets
{format_tickets_for_llm(tickets)}

# Question
{question}

Provide a clear, concise answer with ticket IDs as evidence.\
"""
    return [
        {'role': 'system', 'content': _ASK_SYSTEM_PROMPT},
        {'role': 'user', 'content': user_content},
    ]


def _generate_fallback(tickets: list[Ticket], question: str) -> str:
    """Answer a question without LLM using keyword filtering."""
    words = question.lower()

    # Try status-based filtering
    matched_status = None
    for keyword, status in _STATUS_KEYWORDS.items():
        if keyword in words:
            matched_status = status
            break

    # Try priority-based filtering
    matched_priority = None
    for keyword, priority in _PRIORITY_KEYWORDS.items():
        if keyword in words:
            matched_priority = priority
            break

    # Filter tickets
    filtered = tickets
    if matched_status:
        filtered = [t for t in filtered if t.status == matched_status]
    if matched_priority:
        filtered = [t for t in filtered if t.priority == matched_priority]

    # Try label/title keyword matching if no status/priority match
    if not matched_status and not matched_priority:
        label_words = set(re.findall(r'\w+', words)) - {
            'what',
            'how',
            'many',
            'are',
            'is',
            'the',
            'a',
            'an',
            'in',
            'on',
            'at',
            'to',
            'for',
            'of',
            'with',
            'by',
        }
        if label_words:
            filtered = [
                t
                for t in tickets
                if any(lw in label.lower() for lw in label_words for label in t.labels)
                or any(lw in t.title.lower() for lw in label_words)
            ]

    if not filtered:
        return (
            f'No tickets found matching your query. ({len(tickets)} tickets in scope)'
        )

    # Format response
    lines = [f'Tickets ({len(filtered)}):']
    for t in filtered:
        lines.append(f'  {t.id}  {t.title}')
        lines.append(f'         Status: {t.status} | Priority: {t.priority}')
    lines.append('')
    lines.append('Tip: Configure an LLM backend for richer answers.')
    lines.append("     Run 'oppie config edit' to add LLM settings.")
    return '\n'.join(lines)


def _save_ask_artifact(
    home: Path,
    question: str,
    answer: str,
    run_id: str,
) -> Path:
    """Save ask artifact as JSON."""
    store = ArtifactStore(home)
    content = json.dumps(
        {'question': question, 'answer': answer, 'run_id': run_id},
        indent=2,
    )
    return store.save_artifact(ArtifactType.ASK, content, run_id)


def _append_run_log(
    home: Path,
    run_id: str,
    duration: float,
    artifact_path: Path,
    usage: TokenUsage | None,
) -> None:
    """Append ask entry to run log."""
    run_log = RunLog(home)
    run_log.append(
        RunLogEntry(
            run_id=run_id,
            command='ask',
            timestamp=datetime.now(UTC).isoformat(),
            duration=duration,
            artifact_paths=[str(artifact_path)],
            token_usage=usage.to_dict() if usage else None,
        )
    )
