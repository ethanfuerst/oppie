from unittest.mock import patch

from oppie.models.apply import OperationStatus
from oppie.models.operation import Operation
from oppie.providers.linear.config import LinearProviderConfig
from oppie.providers.linear.provider import LinearProvider
from tests.providers.linear.conftest import make_cache, make_home, make_ticket


def _make_provider(tmp_path):
    home = make_home(tmp_path)
    cache = make_cache(tmp_path)
    config = LinearProviderConfig(type='linear', team_id='t-1', api_key='sk-test')
    provider = LinearProvider(home=home, cache=cache, config=config)
    # Pre-populate lookup caches
    provider._state_map = {'Todo': 'state-1', 'Done': 'state-2'}
    provider._label_map = {'bug': 'lbl-1', 'feature': 'lbl-2'}
    provider._member_map = {'Alice': 'user-1'}
    return provider


def _success_response():
    return {
        'issueUpdate': {
            'success': True,
            'issue': {
                'id': 'u1',
                'identifier': 'ETH-1',
                'updatedAt': '2026-03-01T00:00:00Z',
            },
        }
    }


def test_apply_updates_status(tmp_path):
    provider = _make_provider(tmp_path)
    provider._cache.upsert_ticket(make_ticket('ETH-1', external_id='uuid-1'))
    op = Operation('ETH-1', 'status', 'Todo', 'Done', 'close it')

    with patch.object(provider, '_graphql', return_value=_success_response()):
        results = provider.apply([op])

    assert len(results) == 1
    assert results[0].status == OperationStatus.OK


def test_apply_updates_priority(tmp_path):
    provider = _make_provider(tmp_path)
    provider._cache.upsert_ticket(make_ticket('ETH-1', external_id='uuid-1'))
    op = Operation('ETH-1', 'priority', 'medium', 'high', 'bump')
    calls = []

    def track_graphql(query, variables=None):
        calls.append(variables)
        return _success_response()

    with patch.object(provider, '_graphql', side_effect=track_graphql):
        results = provider.apply([op])

    assert results[0].status == OperationStatus.OK
    assert calls[0]['input'] == {'priority': 2}


def test_apply_updates_owner(tmp_path):
    provider = _make_provider(tmp_path)
    provider._cache.upsert_ticket(make_ticket('ETH-1', external_id='uuid-1'))
    op = Operation('ETH-1', 'owner', None, 'Alice', 'assign')
    calls = []

    def track_graphql(query, variables=None):
        calls.append(variables)
        return _success_response()

    with patch.object(provider, '_graphql', side_effect=track_graphql):
        results = provider.apply([op])

    assert results[0].status == OperationStatus.OK
    assert calls[0]['input'] == {'assigneeId': 'user-1'}


def test_apply_updates_labels(tmp_path):
    provider = _make_provider(tmp_path)
    provider._cache.upsert_ticket(make_ticket('ETH-1', external_id='uuid-1'))
    op = Operation('ETH-1', 'labels', [], ['bug', 'feature'], 'tag')
    calls = []

    def track_graphql(query, variables=None):
        calls.append(variables)
        return _success_response()

    with patch.object(provider, '_graphql', side_effect=track_graphql):
        results = provider.apply([op])

    assert results[0].status == OperationStatus.OK
    assert calls[0]['input'] == {'labelIds': ['lbl-1', 'lbl-2']}


def test_apply_updates_estimate(tmp_path):
    provider = _make_provider(tmp_path)
    provider._cache.upsert_ticket(make_ticket('ETH-1', external_id='uuid-1'))
    op = Operation('ETH-1', 'estimate', None, 5, 'size')
    calls = []

    def track_graphql(query, variables=None):
        calls.append(variables)
        return _success_response()

    with patch.object(provider, '_graphql', side_effect=track_graphql):
        results = provider.apply([op])

    assert results[0].status == OperationStatus.OK
    assert calls[0]['input'] == {'estimate': 5}


def test_apply_missing_ticket_fails(tmp_path):
    provider = _make_provider(tmp_path)
    op = Operation('NOPE-1', 'status', 'Todo', 'Done', 'close')

    results = provider.apply([op])

    assert len(results) == 1
    assert results[0].status == OperationStatus.FAILED
    assert 'not found' in results[0].error


def test_apply_unknown_state_fails(tmp_path):
    provider = _make_provider(tmp_path)
    provider._cache.upsert_ticket(make_ticket('ETH-1', external_id='uuid-1'))
    op = Operation('ETH-1', 'status', 'Todo', 'Nonexistent', 'close')

    results = provider.apply([op])

    assert len(results) == 1
    assert results[0].status == OperationStatus.FAILED
    assert 'Unknown state' in results[0].error


def test_apply_mutation_failure(tmp_path):
    provider = _make_provider(tmp_path)
    provider._cache.upsert_ticket(make_ticket('ETH-1', external_id='uuid-1'))
    op = Operation('ETH-1', 'status', 'Todo', 'Done', 'close')
    fail_response = {'issueUpdate': {'success': False, 'issue': None}}

    with patch.object(provider, '_graphql', return_value=fail_response):
        results = provider.apply([op])

    assert len(results) == 1
    assert results[0].status == OperationStatus.FAILED
    assert 'success=false' in results[0].error
