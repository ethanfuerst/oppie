from pathlib import Path
from unittest.mock import patch

import pytest

from oppie.models.ticket import Ticket, TicketMetadata, TicketSource
from oppie.providers.local import LocalProvider


@pytest.fixture(autouse=True)
def _close_provider():
    """Track and close LocalProvider instances used as cache."""
    providers: list[LocalProvider] = []
    original_init = LocalProvider.__init__

    def tracking_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        providers.append(self)

    with patch.object(LocalProvider, '__init__', tracking_init):
        yield

    for p in providers:
        p.close()


def make_cache(tmp_path: Path) -> LocalProvider:
    home = tmp_path / '.oppie'
    home.mkdir(exist_ok=True)
    (home / 'tickets').mkdir(exist_ok=True)
    (home / 'state').mkdir(exist_ok=True)
    (home / 'state' / 'linear').mkdir(exist_ok=True)
    return LocalProvider(home)


def make_home(tmp_path: Path) -> Path:
    home = tmp_path / '.oppie'
    home.mkdir(exist_ok=True)
    (home / 'tickets').mkdir(exist_ok=True)
    (home / 'state').mkdir(exist_ok=True)
    (home / 'state' / 'linear').mkdir(exist_ok=True)
    return home


def make_ticket(
    ticket_id: str = 'ETH-1',
    title: str = 'Test ticket',
    status: str = 'Todo',
    priority: str = 'medium',
    owner: str | None = None,
    labels: list[str] | None = None,
    project: str | None = None,
    description: str = 'A test ticket',
    external_id: str | None = 'uuid-1',
    estimate: int | None = None,
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
        metadata=TicketMetadata(
            source=TicketSource.LINEAR,
            external_id=external_id,
            synced_at='2026-01-01T00:00:00Z',
        ),
        estimate=estimate,
    )
