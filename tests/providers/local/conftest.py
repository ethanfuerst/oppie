from pathlib import Path
from unittest.mock import patch

import pytest

from oppie.models.ticket import Ticket, TicketMetadata, TicketSource
from oppie.providers.local import LocalProvider


@pytest.fixture(autouse=True)
def _close_provider():
    """Track providers created during a test and close them after."""
    providers: list[LocalProvider] = []
    original_init = LocalProvider.__init__

    def tracking_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        providers.append(self)

    with patch.object(LocalProvider, '__init__', tracking_init):
        yield

    for p in providers:
        p.close()


def make_provider(tmp_path: Path) -> LocalProvider:
    home = tmp_path / '.oppie'
    home.mkdir()
    (home / 'tickets').mkdir()
    (home / 'state').mkdir()
    return LocalProvider(home)


def make_ticket(
    ticket_id: str = 'T-1',
    title: str = 'Test ticket',
    status: str = 'todo',
    priority: str = 'medium',
    owner: str | None = None,
    labels: list[str] | None = None,
    project: str | None = None,
    description: str = 'A test ticket',
) -> Ticket:
    return Ticket(
        id=ticket_id,
        title=title,
        status=status,
        priority=priority,
        owner=owner,
        labels=labels or [],
        created_at='2026-01-01T00:00:00Z',
        updated_at='2026-01-01T00:00:00Z',
        project=project,
        description=description,
        metadata=TicketMetadata(source=TicketSource.LOCAL),
    )
