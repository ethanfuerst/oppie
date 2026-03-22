from oppie.providers.local import TicketFilter
from tests.providers.local.conftest import make_provider, make_ticket


def test_list_tickets_no_filter_returns_all(tmp_path):
    provider = make_provider(tmp_path)
    provider.create_ticket(make_ticket('LIST-1'))
    provider.create_ticket(make_ticket('LIST-2'))
    result = provider.list_tickets()

    assert len(result) == 2
    ids = {t.id for t in result}
    assert ids == {'LIST-1', 'LIST-2'}


def test_list_tickets_filter_by_status(tmp_path):
    provider = make_provider(tmp_path)
    provider.create_ticket(make_ticket('FS-1', status='todo'))
    provider.create_ticket(make_ticket('FS-2', status='in_progress'))
    provider.create_ticket(make_ticket('FS-3', status='todo'))
    result = provider.list_tickets(TicketFilter(status='todo'))

    assert len(result) == 2
    assert all(t.status == 'todo' for t in result)


def test_list_tickets_filter_by_label(tmp_path):
    provider = make_provider(tmp_path)
    provider.create_ticket(make_ticket('FL-1', labels=['bug']))
    provider.create_ticket(make_ticket('FL-2', labels=['feature']))
    provider.create_ticket(make_ticket('FL-3', labels=['bug', 'security']))
    result = provider.list_tickets(TicketFilter(labels=['bug']))

    assert len(result) == 2
    ids = {t.id for t in result}
    assert ids == {'FL-1', 'FL-3'}


def test_list_tickets_multiple_filters_combined_with_and(tmp_path):
    provider = make_provider(tmp_path)
    provider.create_ticket(make_ticket('MF-1', status='todo', priority='high'))
    provider.create_ticket(make_ticket('MF-2', status='todo', priority='low'))
    provider.create_ticket(make_ticket('MF-3', status='done', priority='high'))
    result = provider.list_tickets(TicketFilter(status='todo', priority='high'))

    assert len(result) == 1
    assert result[0].id == 'MF-1'


def test_list_tickets_returns_empty_for_no_matches(tmp_path):
    provider = make_provider(tmp_path)
    provider.create_ticket(make_ticket('NM-1', status='todo'))
    result = provider.list_tickets(TicketFilter(status='done'))

    assert result == []
