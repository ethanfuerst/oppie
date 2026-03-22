import pytest

from tests.providers.local.conftest import make_provider, make_ticket


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
