import json

from oppie.tools.base import Tool, ToolContext, ToolResult


async def _execute_search_tickets(input: dict, context: ToolContext) -> ToolResult:
    """Search tickets by text query, status, priority, owner, or labels."""
    query = input.get('query')
    status = input.get('status')
    priority = input.get('priority')
    owner = input.get('owner')
    labels = input.get('labels')

    # Text search if query provided
    if query:
        tickets = context.provider.search_tickets(query)
    else:
        tickets = context.provider.list_tickets()

    # Apply structured filters
    if status:
        tickets = [t for t in tickets if t.status == status]
    if priority:
        tickets = [t for t in tickets if t.priority == priority]
    if owner:
        tickets = [t for t in tickets if t.owner == owner]
    if labels:
        label_set = set(labels)
        tickets = [t for t in tickets if label_set & set(t.labels)]

    results = [
        {
            'id': t.id,
            'title': t.title,
            'status': t.status,
            'priority': t.priority,
            'owner': t.owner,
            'labels': t.labels,
        }
        for t in tickets
    ]
    return ToolResult(content=json.dumps(results))


async def _execute_get_ticket(input: dict, context: ToolContext) -> ToolResult:
    """Get full details for a single ticket by ID."""
    ticket_id = input['ticket_id']
    ticket = context.provider.read_ticket(ticket_id)
    if ticket is None:
        return ToolResult(content=f'Ticket not found: {ticket_id}', is_error=True)
    return ToolResult(content=json.dumps(ticket.to_dict()))


SEARCH_TICKETS_TOOL = Tool(
    name='search_tickets',
    description=(
        'Search tickets by text query, status, priority, owner, or labels. '
        'Returns a summary list of matching tickets.'
    ),
    schema={
        'type': 'object',
        'properties': {
            'query': {
                'type': 'string',
                'description': 'Text to search in ticket titles and descriptions.',
            },
            'status': {
                'type': 'string',
                'description': 'Filter by status (e.g., open, in_progress, done).',
            },
            'priority': {
                'type': 'string',
                'description': 'Filter by priority (e.g., urgent, high, medium, low).',
            },
            'owner': {
                'type': 'string',
                'description': 'Filter by owner.',
            },
            'labels': {
                'type': 'array',
                'items': {'type': 'string'},
                'description': 'Filter by labels (tickets matching any label).',
            },
        },
    },
    execute=_execute_search_tickets,
    modes={'ask', 'plan'},
)

GET_TICKET_TOOL = Tool(
    name='get_ticket',
    description='Get full details for a single ticket by ID.',
    schema={
        'type': 'object',
        'properties': {
            'ticket_id': {
                'type': 'string',
                'description': 'The ticket ID to look up.',
            },
        },
        'required': ['ticket_id'],
    },
    execute=_execute_get_ticket,
    modes={'ask', 'plan'},
)
