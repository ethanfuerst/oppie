import json

from oppie.tools.base import Tool, ToolContext, ToolResult


async def _execute_propose_operation(input: dict, context: ToolContext) -> ToolResult:
    """Validate and accept a proposed operation on a ticket field."""
    ticket_id = input['ticket_id']
    field = input['field']
    new_value = input['new_value']
    rationale = input.get('rationale', '')

    # Check ticket exists
    ticket = context.provider.read_ticket(ticket_id)
    if ticket is None:
        return ToolResult(content=f'Ticket not found: {ticket_id}', is_error=True)

    # Check field exists
    if not hasattr(ticket, field):
        return ToolResult(
            content=f'Unknown field {field!r} on ticket {ticket_id}', is_error=True
        )

    # Check field is updatable
    cap_error = context.capabilities.validate_operation_value_raw(field, new_value)
    if cap_error:
        return ToolResult(content=cap_error, is_error=True)

    current_value = getattr(ticket, field)
    return ToolResult(
        content=json.dumps(
            {
                'accepted': True,
                'ticket_id': ticket_id,
                'field': field,
                'before_value': current_value,
                'after_value': new_value,
                'rationale': rationale,
            }
        )
    )


PROPOSE_OPERATION_TOOL = Tool(
    name='propose_operation',
    description=(
        'Propose a field-level change to a ticket. '
        'Specify the ticket ID, field name, new value, and rationale.'
    ),
    schema={
        'type': 'object',
        'properties': {
            'ticket_id': {
                'type': 'string',
                'description': 'The ticket ID to modify.',
            },
            'field': {
                'type': 'string',
                'description': 'The field to change (e.g., status, priority, owner).',
            },
            'new_value': {
                'description': 'The new value for the field.',
            },
            'rationale': {
                'type': 'string',
                'description': 'Brief explanation for this change.',
            },
        },
        'required': ['ticket_id', 'field', 'new_value', 'rationale'],
    },
    execute=_execute_propose_operation,
    modes={'plan'},
)
