from unittest.mock import patch

from oppie.providers.linear.config import LinearProviderConfig
from oppie.providers.linear.provider import LinearProvider
from tests.providers.linear.conftest import make_cache, make_home, make_ticket


def _make_provider(tmp_path):
    home = make_home(tmp_path)
    cache = make_cache(tmp_path)
    config = LinearProviderConfig(type='linear', team_id='t-1', api_key='sk-test')
    with patch.object(LinearProvider, '_refresh_lookup_caches'):
        return LinearProvider(home=home, cache=cache, config=config)


def test_read_ticket_delegates(tmp_path):
    provider = _make_provider(tmp_path)
    ticket = make_ticket('DEL-1')
    provider._cache.upsert_ticket(ticket)

    result = provider.read_ticket('DEL-1')

    assert result is not None
    assert result.id == 'DEL-1'


def test_list_tickets_delegates(tmp_path):
    provider = _make_provider(tmp_path)
    provider._cache.upsert_ticket(make_ticket('DEL-2'))
    provider._cache.upsert_ticket(make_ticket('DEL-3'))

    result = provider.list_tickets()

    assert len(result) == 2


def test_capabilities_returns_linear_caps(tmp_path):
    provider = _make_provider(tmp_path)
    caps = provider.capabilities

    assert caps.supports_sync is True
    assert caps.supports_incremental_sync is True
    assert caps.supports_write is True
    assert caps.supports_create is False
    assert caps.supports_projects is True
    assert caps.supports_estimates is True
    assert caps.supports_cycles is True
    assert caps.supports_custom_fields is False
    assert caps.supported_field_updates == [
        'status',
        'priority',
        'owner',
        'labels',
        'estimate',
    ]
