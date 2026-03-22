from tests.providers.local.conftest import make_provider, make_ticket


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
