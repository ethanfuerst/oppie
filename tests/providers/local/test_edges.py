import json
from sqlite3 import ProgrammingError
from unittest.mock import patch

import pytest

from oppie.models.operation import Operation
from oppie.providers.local import TicketFilter
from tests.providers.local.conftest import make_provider, make_ticket


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
        patch(
            'oppie.providers.local.provider.json.dump', side_effect=OSError('disk full')
        ),
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
