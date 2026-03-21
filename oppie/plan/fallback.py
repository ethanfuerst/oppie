import re
from datetime import UTC, datetime

from oppie.models.operation import Operation
from oppie.models.plan import Plan, PlanStatus, compute_plan_id
from oppie.providers.local import LocalProvider

_STATUS_KEYWORDS: dict[str, str] = {
    'close': 'done',
    'finish': 'done',
    'complete': 'done',
    'done': 'done',
    'reopen': 'open',
    'open': 'open',
    'start': 'in_progress',
    'begin': 'in_progress',
    'block': 'blocked',
}

_PRIORITY_KEYWORDS: dict[str, str] = {
    'prioritize': 'high',
    'urgent': 'high',
    'critical': 'high',
    'deprioritize': 'low',
}


def generate_plan_fallback(
    instruction: str,
    provider: LocalProvider,
) -> Plan:
    """Generate a plan without LLM using keyword matching.

    Parse instruction for status/priority keywords, filter tickets,
    and generate simple field-change operations.
    """
    words = set(re.findall(r'\w+', instruction.lower()))
    operations: list[Operation] = []
    tickets = provider.list_tickets()

    # Determine target status change
    target_status: str | None = None
    for keyword, status in _STATUS_KEYWORDS.items():
        if keyword in words:
            target_status = status
            break

    # Determine target priority change
    target_priority: str | None = None
    for keyword, priority in _PRIORITY_KEYWORDS.items():
        if keyword in words:
            target_priority = priority
            break

    # Filter tickets by label keywords (any label word appearing in instruction)
    matching_tickets = tickets
    label_words = words - set(_STATUS_KEYWORDS) - set(_PRIORITY_KEYWORDS)
    if label_words:
        matching_tickets = [
            t
            for t in tickets
            if any(lw in label.lower() for lw in label_words for label in t.labels)
            or any(lw in t.title.lower() for lw in label_words)
        ]
        # Fall back to all tickets if no label match
        if not matching_tickets:
            matching_tickets = tickets

    for ticket in matching_tickets:
        if target_status and ticket.status != target_status:
            operations.append(
                Operation(
                    ticket_id=ticket.id,
                    field='status',
                    before_value=ticket.status,
                    after_value=target_status,
                    rationale=f'Keyword match: set status to {target_status}',
                )
            )
        if target_priority and ticket.priority != target_priority:
            operations.append(
                Operation(
                    ticket_id=ticket.id,
                    field='priority',
                    before_value=ticket.priority,
                    after_value=target_priority,
                    rationale=f'Keyword match: set priority to {target_priority}',
                )
            )

    plan_id = compute_plan_id(operations)
    return Plan(
        plan_id=plan_id,
        instruction=instruction,
        operations=operations,
        risks=['Generated without LLM — operations based on keyword matching only'],
        created_at=datetime.now(UTC).isoformat(),
        status=PlanStatus.SAVED,
    )
