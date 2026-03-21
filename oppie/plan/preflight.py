from oppie.models.operation import Operation
from oppie.providers.local import LocalProvider


def run_preflight(
    operations: list[Operation],
    provider: LocalProvider,
) -> list[str]:
    """Validate operations against provider capabilities and ticket state.

    For each operation:
    1. Check provider capabilities support the field update.
    2. Verify the ticket exists.
    3. Overwrite before_value with the actual ticket value (LLM may hallucinate).

    Return a list of error strings. Empty list means all valid.
    """
    capabilities = provider.capabilities
    errors: list[str] = []

    for op in operations:
        # Capability check
        cap_error = capabilities.validate_operation(op)
        if cap_error:
            errors.append(f'[{op.ticket_id}.{op.field}] {cap_error}')
            continue

        # Ticket existence check
        ticket = provider.read_ticket(op.ticket_id)
        if ticket is None:
            errors.append(
                f'[{op.ticket_id}.{op.field}] Ticket not found: {op.ticket_id}'
            )
            continue

        # Overwrite before_value with actual value
        if not hasattr(ticket, op.field):
            errors.append(
                f'[{op.ticket_id}.{op.field}] Unknown field {op.field!r} on ticket'
            )
            continue
        op.before_value = getattr(ticket, op.field)

    return errors
