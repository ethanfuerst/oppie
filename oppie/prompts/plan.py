from oppie.models.plan import Plan
from oppie.models.ticket import Ticket

SYSTEM_PROMPT = """\
You are oppie, a ticket operations bot that uses a plan/apply workflow.
You receive a set of tickets and a user instruction, then generate a plan \
consisting of explicit field-level operations on those tickets.

Rules:
- Each operation targets exactly one ticket and one field.
- Include before_value (current) and after_value (proposed) for every operation.
- Include a short rationale for each operation.
- Identify risks or concerns with the proposed changes.
- Only propose operations that are actionable — do not suggest vague changes.
- If the instruction is ambiguous, propose the most conservative interpretation.\
"""


def _format_tickets(tickets: list[Ticket]) -> str:
    """Format tickets as a compact text block for the LLM prompt."""
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


def _format_past_plans(plans: list[Plan]) -> str:
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


def _format_context(context: dict[str, str]) -> str:
    """Format context docs (vision, roadmap, etc.) for the prompt."""
    if not context:
        return ''
    parts = []
    for name, content in context.items():
        parts.append(f'## {name.replace("_", " ").title()}\n{content}')
    return '\n\n'.join(parts)


def build_plan_prompt(
    instruction: str,
    context: dict[str, str],
    tickets: list[Ticket],
    past_plans: list[Plan],
) -> list[dict]:
    """Build OpenAI-format messages for plan generation.

    Args:
        instruction: The user's intent string.
        context: Dict of context doc name -> content (e.g. 'vision' -> '...').
        tickets: Current tickets in scope.
        past_plans: Up to 3 similar past plans for few-shot context.

    Returns:
        List of message dicts with 'role' and 'content' keys.
    """
    context_section = _format_context(context)
    context_block = f'\n# Context\n{context_section}\n' if context_section else ''

    user_content = f"""\
{context_block}
# Current tickets
{_format_tickets(tickets)}

# Past similar plans
{_format_past_plans(past_plans)}

# User instruction
{instruction}

Generate a plan with explicit operations (ticket_id, field, before_value, \
after_value, rationale) and a list of risks.\
"""

    return [
        {'role': 'system', 'content': SYSTEM_PROMPT},
        {'role': 'user', 'content': user_content},
    ]
