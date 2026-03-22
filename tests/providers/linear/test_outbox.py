from unittest.mock import patch

from oppie.models.apply import OperationStatus
from oppie.models.operation import Operation
from oppie.models.ticket import TicketMetadata, TicketSource
from oppie.providers.linear.config import LinearProviderConfig
from oppie.providers.linear.provider import LinearProvider
from tests.providers.linear.conftest import make_cache, make_home, make_ticket


def _make_provider(tmp_path):
    home = make_home(tmp_path)
    cache = make_cache(tmp_path)
    config = LinearProviderConfig(type='linear', team_id='t-1', api_key='sk-test')
    provider = LinearProvider(home=home, cache=cache, config=config)
    provider._state_map = {'Todo': 'state-1', 'Done': 'state-2'}
    provider._label_map = {}
    provider._member_map = {}
    return provider


def test_update_ticket_queues_outbox(tmp_path):
    provider = _make_provider(tmp_path)
    ticket = make_ticket('ETH-1', status='Todo', external_id='uuid-1')
    provider._cache.upsert_ticket(ticket)

    provider.update_ticket('ETH-1', {'status': 'Done'})

    ops = provider._read_outbox()

    assert len(ops) == 1
    assert ops[0].ticket_id == 'ETH-1'
    assert ops[0].field == 'status'


def test_update_ticket_skips_outbox_for_local(tmp_path):
    provider = _make_provider(tmp_path)
    from oppie.models.ticket import Ticket

    local_ticket = Ticket(
        id='LOCAL-1',
        title='Local ticket',
        status='todo',
        priority='medium',
        owner=None,
        labels=[],
        created_at='2026-01-01T00:00:00Z',
        updated_at='2026-01-01T00:00:00Z',
        project=None,
        description='local',
        metadata=TicketMetadata(source=TicketSource.LOCAL),
    )
    provider._cache.upsert_ticket(local_ticket)

    provider.update_ticket('LOCAL-1', {'status': 'done'})

    ops = provider._read_outbox()

    assert len(ops) == 0


def test_flush_outbox_sends_and_clears(tmp_path):
    provider = _make_provider(tmp_path)
    provider._cache.upsert_ticket(make_ticket('ETH-1', external_id='uuid-1'))
    op = Operation('ETH-1', 'status', 'Todo', 'Done', 'close')
    provider._append_outbox(op)

    success_response = {
        'issueUpdate': {
            'success': True,
            'issue': {
                'id': 'uuid-1',
                'identifier': 'ETH-1',
                'updatedAt': '2026-03-01T00:00:00Z',
            },
        },
    }
    with patch.object(provider, '_graphql', return_value=success_response):
        results = provider.flush_outbox()

    assert len(results) == 1
    assert results[0].status == OperationStatus.OK
    assert not provider._outbox_path.exists()


def test_flush_outbox_keeps_failed(tmp_path):
    provider = _make_provider(tmp_path)
    provider._cache.upsert_ticket(make_ticket('ETH-1', external_id='uuid-1'))
    provider._cache.upsert_ticket(make_ticket('ETH-2', external_id='uuid-2'))

    op1 = Operation('ETH-1', 'status', 'Todo', 'Done', 'close')
    op2 = Operation('ETH-2', 'status', 'Todo', 'Done', 'close')
    provider._append_outbox(op1)
    provider._append_outbox(op2)

    call_count = 0

    def alternating_graphql(query, variables=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {
                'issueUpdate': {
                    'success': True,
                    'issue': {'id': 'uuid-1', 'identifier': 'ETH-1', 'updatedAt': 'x'},
                }
            }
        return {'issueUpdate': {'success': False, 'issue': None}}

    with patch.object(provider, '_graphql', side_effect=alternating_graphql):
        results = provider.flush_outbox()

    assert len(results) == 2
    remaining = provider._read_outbox()

    assert len(remaining) == 1
    assert remaining[0].ticket_id == 'ETH-2'


def test_flush_empty_outbox(tmp_path):
    provider = _make_provider(tmp_path)

    results = provider.flush_outbox()

    assert results == []
