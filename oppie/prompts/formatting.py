import logging
from pathlib import Path

from oppie.models.plan import Plan
from oppie.models.ticket import Ticket

logger = logging.getLogger(__name__)

CONTEXT_DOC_NAMES = ('vision', 'roadmap', 'metrics', 'prioritization')


def load_context(home: Path) -> dict[str, str]:
    """Read optional context docs from {home}/context/."""
    context_dir = home / 'context'
    if not context_dir.is_dir():
        return {}
    context = {}
    for name in CONTEXT_DOC_NAMES:
        path = context_dir / f'{name}.md'
        if path.exists():
            content = path.read_text().strip()
            if content:
                context[name] = content
    return context


def format_tickets_for_llm(tickets: list[Ticket]) -> str:
    """Format tickets as a compact text block for LLM prompts."""
    if not tickets:
        return '(no tickets)'
    lines = []
    for t in tickets:
        labels = ', '.join(t.labels) if t.labels else 'none'
        lines.append(
            f'- [{t.id}] {t.title} | status={t.status} priority={t.priority} '
            f'owner={t.owner or "unassigned"} labels={labels}'
        )
    return '\n'.join(lines)


def format_context_for_llm(context: dict[str, str]) -> str:
    """Format context docs (vision, roadmap, etc.) for LLM prompts."""
    if not context:
        return ''
    parts = []
    for name, content in context.items():
        parts.append(f'## {name.replace("_", " ").title()}\n{content}')
    return '\n\n'.join(parts)


def format_past_plans(plans: list[Plan]) -> str:
    """Format past similar plans as context for the LLM."""
    if not plans:
        return '(no similar past plans)'
    parts = []
    for p in plans:
        ops_summary = '; '.join(
            f'{op.ticket_id}.{op.field}: {op.before_value!r} -> {op.after_value!r}'
            for op in p.operations
        )
        parts.append(f'- Plan {p.plan_id}: "{p.instruction}" -> [{ops_summary}]')
    return '\n'.join(parts)
