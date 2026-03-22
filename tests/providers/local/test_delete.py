from tests.providers.local.conftest import make_provider, make_ticket


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
