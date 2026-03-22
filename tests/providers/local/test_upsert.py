from tests.providers.local.conftest import make_provider, make_ticket


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
