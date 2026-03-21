import json
from pathlib import Path
from sqlite3 import ProgrammingError
from unittest.mock import patch

import pytest

from oppie.models.operation import Operation
from oppie.models.ticket import Ticket, TicketMetadata, TicketSource
from oppie.providers.local import LocalProvider, TicketFilter


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


# --- create_ticket ---


def test_create_ticket_writes_json_file(tmp_path):
    provider = make_provider(tmp_path)
    ticket = make_ticket('CREATE-1')
    result = provider.create_ticket(ticket)

    assert result == ticket
    path = tmp_path / '.oppie' / 'tickets' / 'CREATE-1.json'
    assert path.exists()
    data = json.loads(path.read_text())
    assert data['id'] == 'CREATE-1'
    assert data['schema_version'] == 'v1'


def test_create_ticket_raises_on_duplicate(tmp_path):
    provider = make_provider(tmp_path)
    ticket = make_ticket('DUP-1')
    provider.create_ticket(ticket)

    with pytest.raises(FileExistsError, match='Ticket already exists'):
        provider.create_ticket(ticket)


# --- read_ticket ---


def test_read_ticket_returns_ticket(tmp_path):
    provider = make_provider(tmp_path)
    ticket = make_ticket('READ-1', title='Read me')
    provider.create_ticket(ticket)
    result = provider.read_ticket('READ-1')

    assert result is not None
    assert result.id == 'READ-1'
    assert result.title == 'Read me'


def test_read_ticket_returns_none_for_missing(tmp_path):
    provider = make_provider(tmp_path)

    assert provider.read_ticket('NOPE') is None


# --- update_ticket ---


def test_update_ticket_modifies_and_persists(tmp_path):
    provider = make_provider(tmp_path)
    provider.create_ticket(make_ticket('UPD-1', status='todo'))
    result = provider.update_ticket('UPD-1', {'status': 'in_progress'})

    assert result.status == 'in_progress'

    reloaded = provider.read_ticket('UPD-1')
    assert reloaded is not None
    assert reloaded.status == 'in_progress'


def test_update_ticket_raises_for_missing(tmp_path):
    provider = make_provider(tmp_path)

    with pytest.raises(FileNotFoundError, match='Ticket not found'):
        provider.update_ticket('NOPE', {'status': 'done'})


def test_update_ticket_raises_for_protected_field_id(tmp_path):
    provider = make_provider(tmp_path)
    provider.create_ticket(make_ticket('PROT-1'))

    with pytest.raises(ValueError, match='Cannot update field'):
        provider.update_ticket('PROT-1', {'id': 'NEW-ID'})


def test_update_ticket_raises_for_protected_field_metadata(tmp_path):
    provider = make_provider(tmp_path)
    provider.create_ticket(make_ticket('PROT-2'))

    with pytest.raises(ValueError, match='Cannot update field'):
        provider.update_ticket('PROT-2', {'metadata': {}})


def test_update_ticket_raises_for_unknown_field(tmp_path):
    provider = make_provider(tmp_path)
    provider.create_ticket(make_ticket('UNK-1'))

    with pytest.raises(ValueError, match='Unknown ticket field'):
        provider.update_ticket('UNK-1', {'nonexistent': 'value'})


# --- delete_ticket ---


def test_delete_ticket_removes_file(tmp_path):
    provider = make_provider(tmp_path)
    provider.create_ticket(make_ticket('DEL-1'))

    assert provider.delete_ticket('DEL-1') is True

    path = tmp_path / '.oppie' / 'tickets' / 'DEL-1.json'
    assert not path.exists()
    assert provider.read_ticket('DEL-1') is None


def test_delete_ticket_returns_false_for_missing(tmp_path):
    provider = make_provider(tmp_path)

    assert provider.delete_ticket('NOPE') is False


# --- list_tickets ---


def test_list_tickets_no_filter_returns_all(tmp_path):
    provider = make_provider(tmp_path)
    provider.create_ticket(make_ticket('LIST-1'))
    provider.create_ticket(make_ticket('LIST-2'))
    result = provider.list_tickets()

    assert len(result) == 2
    ids = {t.id for t in result}
    assert ids == {'LIST-1', 'LIST-2'}


def test_list_tickets_filter_by_status(tmp_path):
    provider = make_provider(tmp_path)
    provider.create_ticket(make_ticket('FS-1', status='todo'))
    provider.create_ticket(make_ticket('FS-2', status='in_progress'))
    provider.create_ticket(make_ticket('FS-3', status='todo'))
    result = provider.list_tickets(TicketFilter(status='todo'))

    assert len(result) == 2
    assert all(t.status == 'todo' for t in result)


def test_list_tickets_filter_by_label(tmp_path):
    provider = make_provider(tmp_path)
    provider.create_ticket(make_ticket('FL-1', labels=['bug']))
    provider.create_ticket(make_ticket('FL-2', labels=['feature']))
    provider.create_ticket(make_ticket('FL-3', labels=['bug', 'security']))
    result = provider.list_tickets(TicketFilter(labels=['bug']))

    assert len(result) == 2
    ids = {t.id for t in result}
    assert ids == {'FL-1', 'FL-3'}


def test_list_tickets_multiple_filters_combined_with_and(tmp_path):
    provider = make_provider(tmp_path)
    provider.create_ticket(make_ticket('MF-1', status='todo', priority='high'))
    provider.create_ticket(make_ticket('MF-2', status='todo', priority='low'))
    provider.create_ticket(make_ticket('MF-3', status='done', priority='high'))
    result = provider.list_tickets(TicketFilter(status='todo', priority='high'))

    assert len(result) == 1
    assert result[0].id == 'MF-1'


def test_list_tickets_returns_empty_for_no_matches(tmp_path):
    provider = make_provider(tmp_path)
    provider.create_ticket(make_ticket('NM-1', status='todo'))
    result = provider.list_tickets(TicketFilter(status='done'))

    assert result == []


# --- search_tickets ---


def test_search_tickets_matches_title(tmp_path):
    provider = make_provider(tmp_path)
    provider.create_ticket(make_ticket('ST-1', title='Fix login bug'))
    provider.create_ticket(make_ticket('ST-2', title='Add feature'))
    result = provider.search_tickets('login')

    assert len(result) == 1
    assert result[0].id == 'ST-1'


def test_search_tickets_matches_description(tmp_path):
    provider = make_provider(tmp_path)
    provider.create_ticket(
        make_ticket('SD-1', title='Bug', description='Users cannot authenticate')
    )
    provider.create_ticket(
        make_ticket('SD-2', title='Feature', description='Add dashboard')
    )
    result = provider.search_tickets('authenticate')

    assert len(result) == 1
    assert result[0].id == 'SD-1'


def test_search_tickets_returns_empty_for_no_matches(tmp_path):
    provider = make_provider(tmp_path)
    provider.create_ticket(make_ticket('SE-1', title='Some ticket'))
    result = provider.search_tickets('zzzznotfound')

    assert result == []


def test_search_tickets_case_insensitive(tmp_path):
    provider = make_provider(tmp_path)
    provider.create_ticket(make_ticket('CI-1', title='Fix Login Bug'))
    result = provider.search_tickets('fix login')

    assert len(result) == 1
    assert result[0].id == 'CI-1'


# --- upsert_ticket ---


def test_upsert_ticket_creates_if_not_exists(tmp_path):
    provider = make_provider(tmp_path)
    ticket = make_ticket('UP-1')
    result = provider.upsert_ticket(ticket)

    assert result == ticket
    assert provider.read_ticket('UP-1') is not None


def test_upsert_ticket_overwrites_if_exists(tmp_path):
    provider = make_provider(tmp_path)
    provider.upsert_ticket(make_ticket('UP-2', title='Original'))
    provider.upsert_ticket(make_ticket('UP-2', title='Updated'))
    result = provider.read_ticket('UP-2')

    assert result is not None
    assert result.title == 'Updated'


# --- edge cases ---


def test_read_ticket_raises_on_corrupt_json(tmp_path):
    provider = make_provider(tmp_path)
    corrupt_path = tmp_path / '.oppie' / 'tickets' / 'BAD-1.json'
    corrupt_path.write_text('not valid json{{{')

    with pytest.raises(json.JSONDecodeError):
        provider.read_ticket('BAD-1')


def test_atomic_write_cleans_up_temp_on_failure(tmp_path):
    provider = make_provider(tmp_path)
    tickets_dir = tmp_path / '.oppie' / 'tickets'

    ticket = make_ticket('ATOM-1')
    with (
        patch('oppie.providers.local.json.dump', side_effect=OSError('disk full')),
        pytest.raises(OSError, match='disk full'),
    ):
        provider.create_ticket(ticket)

    # Verify no .tmp files remain after failed write
    tmp_files = list(tickets_dir.glob('*.tmp'))
    assert tmp_files == []

    # Verify the target file was not created
    assert not (tickets_dir / 'ATOM-1.json').exists()


def test_close_closes_connection(tmp_path):
    provider = make_provider(tmp_path)
    provider.close()

    # Connection is closed — executing a query should raise
    with pytest.raises(ProgrammingError):
        provider._conn.execute('SELECT 1')


def test_sqlite_index_stays_in_sync(tmp_path):
    provider = make_provider(tmp_path)

    # Create
    provider.create_ticket(make_ticket('SYNC-1', status='todo', labels=['bug']))
    result = provider.list_tickets(TicketFilter(status='todo'))
    assert len(result) == 1

    # Update
    provider.update_ticket('SYNC-1', {'status': 'done'})
    assert provider.list_tickets(TicketFilter(status='todo')) == []
    assert len(provider.list_tickets(TicketFilter(status='done'))) == 1

    # Verify label index updated
    assert len(provider.list_tickets(TicketFilter(labels=['bug']))) == 1

    # Delete
    provider.delete_ticket('SYNC-1')
    assert provider.list_tickets(TicketFilter(status='done')) == []
    assert provider.list_tickets(TicketFilter(labels=['bug'])) == []


# --- capabilities ---


def test_local_provider_capabilities_supports_write(tmp_path):
    provider = make_provider(tmp_path)

    caps = provider.capabilities

    assert caps.supports_write is True
    assert caps.supports_create is True
    assert 'status' in caps.supported_field_updates
    assert 'priority' in caps.supported_field_updates
    assert 'id' not in caps.supported_field_updates
    assert 'metadata' not in caps.supported_field_updates


def test_local_provider_capabilities_validates_operations(tmp_path):
    provider = make_provider(tmp_path)
    op = Operation('T-1', 'status', 'open', 'done', 'test')

    result = provider.capabilities.validate_operation(op)

    assert result is None


def test_local_provider_capabilities_rejects_unsupported_field(tmp_path):
    provider = make_provider(tmp_path)
    op = Operation('T-1', 'fake_field', None, 'val', 'test')

    result = provider.capabilities.validate_operation(op)

    assert result is not None
    assert 'fake_field' in result
