import json

from oppie.models.ticket import Ticket, TicketMetadata, TicketSource


def make_ticket(
    ticket_id, status='open', priority='medium', labels=None, owner='alice'
):
    return Ticket(
        id=ticket_id,
        title=f'Ticket {ticket_id}',
        status=status,
        priority=priority,
        owner=owner,
        labels=labels or [],
        created_at='2026-01-01T00:00:00Z',
        updated_at='2026-01-01T00:00:00Z',
        project='proj',
        description=f'Description for {ticket_id}',
        metadata=TicketMetadata(source=TicketSource.LOCAL),
    )


def write_ticket(home, ticket):
    """Write a ticket JSON file to the instance."""
    path = home / 'tickets' / f'{ticket.id}.json'
    path.write_text(json.dumps(ticket.to_dict(), indent=2) + '\n')


def setup_instance(tmp_path):
    """Create minimal instance directory structure."""
    for d in [
        'tickets',
        'context',
        'artifacts/plans',
        'artifacts/applies',
        'state',
        'logs',
    ]:
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    return tmp_path
