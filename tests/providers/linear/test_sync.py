import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from oppie.providers.base import ProviderNetworkError
from oppie.providers.linear.config import LinearProviderConfig
from oppie.providers.linear.provider import LinearAPIError, LinearProvider
from tests.providers.linear.conftest import make_cache, make_home


def _make_issue_node(
    identifier='ETH-1',
    node_id='uuid-1',
    title='Test issue',
    status_name='Todo',
    priority=3,
    updated_at='2026-03-01T00:00:00Z',
):
    return {
        'id': node_id,
        'identifier': identifier,
        'title': title,
        'description': 'A test issue',
        'state': {'id': 'state-1', 'name': status_name},
        'priority': priority,
        'assignee': {'id': 'user-1', 'name': 'Alice'},
        'labels': {'nodes': [{'id': 'lbl-1', 'name': 'bug'}]},
        'project': {'id': 'proj-1', 'name': 'oppie'},
        'estimate': 5,
        'createdAt': '2026-01-01T00:00:00Z',
        'updatedAt': updated_at,
    }


def _make_page(nodes, has_next=False, end_cursor=None):
    return {
        'team': {
            'issues': {
                'pageInfo': {
                    'hasNextPage': has_next,
                    'endCursor': end_cursor,
                },
                'nodes': nodes,
            },
        },
    }


def _lookup_data():
    return {
        'team': {
            'states': {'nodes': [{'id': 'state-1', 'name': 'Todo'}]},
            'labels': {'nodes': [{'id': 'lbl-1', 'name': 'bug'}]},
            'members': {'nodes': [{'id': 'user-1', 'name': 'Alice'}]},
        },
    }


def _make_provider(tmp_path, **config_kwargs):
    home = make_home(tmp_path)
    cache = make_cache(tmp_path)
    kwargs = {'type': 'linear', 'team_id': 't-1', 'api_key': 'sk-test'}
    kwargs.update(config_kwargs)
    config = LinearProviderConfig(**kwargs)
    return LinearProvider(home=home, cache=cache, config=config)


def test_sync_full_fetches_all_pages(tmp_path):
    provider = _make_provider(tmp_path)
    page1 = _make_page(
        [_make_issue_node('ETH-1', 'u1', updated_at='2026-03-01T00:00:00Z')],
        has_next=True,
        end_cursor='cursor-1',
    )
    page2 = _make_page(
        [_make_issue_node('ETH-2', 'u2', updated_at='2026-03-02T00:00:00Z')],
    )
    responses = [_lookup_data(), _lookup_data(), _lookup_data(), page1, page2]
    with patch.object(provider, '_graphql', side_effect=responses):
        result = provider.sync()

    assert result.tickets_upserted == 2
    assert provider._cache.read_ticket('ETH-1') is not None
    assert provider._cache.read_ticket('ETH-2') is not None


def test_sync_incremental_uses_checkpoint(tmp_path):
    provider = _make_provider(tmp_path)
    page = _make_page(
        [_make_issue_node('ETH-1', updated_at='2026-03-05T00:00:00Z')],
    )
    calls = []

    def tracking_graphql(query, variables=None):
        calls.append((query, variables))
        if 'Issues' in query:
            return page
        return _lookup_data()

    with patch.object(provider, '_graphql', side_effect=tracking_graphql):
        provider.sync(checkpoint='2026-03-01T00:00:00Z')

    # Find the Issues call and check filter
    issues_call = next(c for c in calls if 'Issues' in c[0])

    assert 'filter' in issues_call[1]
    assert issues_call[1]['filter']['updatedAt'] == {'gte': '2026-03-01T00:00:00Z'}


def test_sync_saves_checkpoint(tmp_path):
    provider = _make_provider(tmp_path)
    page = _make_page(
        [_make_issue_node('ETH-1', updated_at='2026-03-10T00:00:00Z')],
    )
    responses = [_lookup_data(), _lookup_data(), _lookup_data(), page]
    with patch.object(provider, '_graphql', side_effect=responses):
        provider.sync()

    checkpoint_path = provider._checkpoint_path

    assert checkpoint_path.exists()
    data = json.loads(checkpoint_path.read_text())
    assert data['checkpoint'] == '2026-03-10T00:00:00Z'


def test_sync_loads_previous_checkpoint(tmp_path):
    provider = _make_provider(tmp_path)
    # Write a checkpoint
    provider._save_checkpoint('2026-03-05T00:00:00Z')

    page = _make_page(
        [_make_issue_node('ETH-1', updated_at='2026-03-06T00:00:00Z')],
    )
    calls = []

    def tracking_graphql(query, variables=None):
        calls.append((query, variables))
        if 'Issues' in query:
            return page
        return _lookup_data()

    with patch.object(provider, '_graphql', side_effect=tracking_graphql):
        provider.sync()

    issues_call = next(c for c in calls if 'Issues' in c[0])

    assert issues_call[1]['filter']['updatedAt'] == {'gte': '2026-03-05T00:00:00Z'}


def test_sync_maps_fields_correctly(tmp_path):
    provider = _make_provider(tmp_path)
    node = _make_issue_node(
        'ETH-42',
        'uuid-42',
        title='Map test',
        status_name='In Progress',
        priority=2,
        updated_at='2026-03-01T00:00:00Z',
    )
    page = _make_page([node])
    responses = [_lookup_data(), _lookup_data(), _lookup_data(), page]
    with patch.object(provider, '_graphql', side_effect=responses):
        provider.sync()

    ticket = provider._cache.read_ticket('ETH-42')

    assert ticket is not None
    assert ticket.title == 'Map test'
    assert ticket.status == 'In Progress'
    assert ticket.priority == 'high'
    assert ticket.owner == 'Alice'
    assert ticket.labels == ['bug']
    assert ticket.project == 'oppie'
    assert ticket.estimate == 5
    assert ticket.metadata.external_id == 'uuid-42'


def test_sync_handles_api_error(tmp_path):
    provider = _make_provider(tmp_path)

    def error_graphql(query, variables=None):
        if 'Issues' in query:
            raise LinearAPIError('Authentication failed.', status_code=401)
        return _lookup_data()

    with patch.object(provider, '_graphql', side_effect=error_graphql):
        result = provider.sync()

    assert result.tickets_upserted == 0
    assert len(result.errors) == 1
    assert 'Authentication failed.' in result.errors[0]


def test_sync_handles_rate_limit(tmp_path):
    provider = _make_provider(tmp_path)
    from oppie.providers.linear.provider import LinearRateLimitError

    def rate_limit_graphql(query, variables=None):
        if 'Issues' in query:
            raise LinearRateLimitError('Rate limited.', retry_after=60.0)
        return _lookup_data()

    with patch.object(provider, '_graphql', side_effect=rate_limit_graphql):
        result = provider.sync()

    assert result.tickets_upserted == 0
    assert len(result.errors) == 1
    assert 'Rate limited.' in result.errors[0]


def test_sync_skips_bad_issue(tmp_path):
    provider = _make_provider(tmp_path)
    good_node = _make_issue_node('ETH-1', 'u1', updated_at='2026-03-01T00:00:00Z')
    bad_node = {'id': 'u2', 'identifier': 'ETH-2'}  # missing required fields
    page = _make_page([good_node, bad_node])
    responses = [_lookup_data(), _lookup_data(), _lookup_data(), page]
    with patch.object(provider, '_graphql', side_effect=responses):
        result = provider.sync()

    assert result.tickets_upserted == 1
    assert len(result.errors) == 1
    assert 'ETH-2' in result.errors[0]


def test_sync_filters_by_project(tmp_path):
    provider = _make_provider(tmp_path, project_id='proj-123')
    page = _make_page([])
    calls = []

    def tracking_graphql(query, variables=None):
        calls.append((query, variables))
        if 'Issues' in query:
            return page
        return _lookup_data()

    with patch.object(provider, '_graphql', side_effect=tracking_graphql):
        provider.sync()

    issues_call = next(c for c in calls if 'Issues' in c[0])

    assert issues_call[1]['filter']['project'] == {'id': {'eq': 'proj-123'}}


def test_sync_filters_by_statuses(tmp_path):
    provider = _make_provider(tmp_path, sync_statuses=['Todo', 'In Progress'])
    page = _make_page([])
    calls = []

    def tracking_graphql(query, variables=None):
        calls.append((query, variables))
        if 'Issues' in query:
            return page
        return _lookup_data()

    with patch.object(provider, '_graphql', side_effect=tracking_graphql):
        provider.sync()

    issues_call = next(c for c in calls if 'Issues' in c[0])

    assert issues_call[1]['filter']['state'] == {
        'name': {'in': ['Todo', 'In Progress']}
    }


def test_sync_filters_by_labels(tmp_path):
    provider = _make_provider(tmp_path, sync_labels=['backend'])
    page = _make_page([])
    calls = []

    def tracking_graphql(query, variables=None):
        calls.append((query, variables))
        if 'Issues' in query:
            return page
        return _lookup_data()

    with patch.object(provider, '_graphql', side_effect=tracking_graphql):
        provider.sync()

    issues_call = next(c for c in calls if 'Issues' in c[0])

    assert issues_call[1]['filter']['labels'] == {'name': {'in': ['backend']}}


def test_sync_combines_filters(tmp_path):
    provider = _make_provider(
        tmp_path,
        project_id='proj-1',
        sync_statuses=['Todo'],
        sync_labels=['bug'],
    )
    page = _make_page([])
    calls = []

    def tracking_graphql(query, variables=None):
        calls.append((query, variables))
        if 'Issues' in query:
            return page
        return _lookup_data()

    with patch.object(provider, '_graphql', side_effect=tracking_graphql):
        provider.sync(checkpoint='2026-03-01T00:00:00Z')

    issues_call = next(c for c in calls if 'Issues' in c[0])
    f = issues_call[1]['filter']

    assert f['updatedAt'] == {'gte': '2026-03-01T00:00:00Z'}
    assert f['project'] == {'id': {'eq': 'proj-1'}}
    assert f['state'] == {'name': {'in': ['Todo']}}
    assert f['labels'] == {'name': {'in': ['bug']}}


def test_graphql_wraps_httpx_error(tmp_path):
    provider = _make_provider(tmp_path)
    provider._client = MagicMock()
    provider._client.post.side_effect = httpx.ConnectError('boom')

    with pytest.raises(ProviderNetworkError) as exc_info:
        provider._graphql('{ viewer { id } }')

    assert 'Network error' in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, httpx.ConnectError)


def test_graphql_wraps_http_status_error(tmp_path):
    provider = _make_provider(tmp_path)
    provider._client = MagicMock()
    resp = MagicMock()
    resp.status_code = 500
    resp.headers = {}
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        '500', request=MagicMock(), response=resp
    )
    provider._client.post.return_value = resp

    with pytest.raises(ProviderNetworkError):
        provider._graphql('{ viewer { id } }')
