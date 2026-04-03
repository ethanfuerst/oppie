from unittest.mock import MagicMock

from oppie.providers.base import ExternalProvider, TicketProvider
from oppie.sync import auto_sync


def test_auto_sync_no_sync_flag():
    provider = MagicMock()
    provider.list_tickets.return_value = [1, 2, 3]

    result = auto_sync(provider, no_sync=True)

    assert not result.synced
    assert result.ticket_count == 3
    assert result.error is None


def test_auto_sync_local_provider():
    """Local-only provider skips sync."""
    provider = MagicMock(spec=TicketProvider)
    provider.list_tickets.return_value = [1, 2]

    result = auto_sync(provider)

    assert not result.synced
    assert result.ticket_count == 2


def test_auto_sync_external_provider_success():
    provider = MagicMock(spec=ExternalProvider)
    provider.sync.return_value = MagicMock()
    provider.list_tickets.return_value = [1, 2, 3, 4, 5]

    result = auto_sync(provider)

    assert result.synced
    assert result.ticket_count == 5
    assert result.error is None


def test_auto_sync_external_provider_failure():
    provider = MagicMock(spec=ExternalProvider)
    provider.sync.side_effect = ConnectionError('timeout')
    provider.list_tickets.return_value = [1, 2]

    result = auto_sync(provider)

    assert not result.synced
    assert result.ticket_count == 2
    assert 'timeout' in result.error
