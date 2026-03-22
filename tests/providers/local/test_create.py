import json

import pytest

from tests.providers.local.conftest import make_provider, make_ticket


def test_create_ticket_writes_json_file(tmp_path):
    provider = make_provider(tmp_path)
    ticket = make_ticket('CREATE-1')
    result = provider.create_ticket(ticket)

    assert result == ticket
    path = tmp_path / '.oppie' / 'tickets' / 'CREATE-1.json'
    assert path.exists()
    data = json.loads(path.read_text())
    assert data['id'] == 'CREATE-1'
    assert data['schema_version'] == 'v1'


def test_create_ticket_raises_on_duplicate(tmp_path):
    provider = make_provider(tmp_path)
    ticket = make_ticket('DUP-1')
    provider.create_ticket(ticket)

    with pytest.raises(FileExistsError, match='Ticket already exists'):
        provider.create_ticket(ticket)
