from tests.providers.local.conftest import make_provider, make_ticket


def test_search_tickets_matches_title(tmp_path):
    provider = make_provider(tmp_path)
    provider.create_ticket(make_ticket('ST-1', title='Fix login bug'))
    provider.create_ticket(make_ticket('ST-2', title='Add feature'))
    result = provider.search_tickets('login')

    assert len(result) == 1
    assert result[0].id == 'ST-1'


def test_search_tickets_matches_description(tmp_path):
    provider = make_provider(tmp_path)
    provider.create_ticket(
        make_ticket('SD-1', title='Bug', description='Users cannot authenticate')
    )
    provider.create_ticket(
        make_ticket('SD-2', title='Feature', description='Add dashboard')
    )
    result = provider.search_tickets('authenticate')

    assert len(result) == 1
    assert result[0].id == 'SD-1'


def test_search_tickets_returns_empty_for_no_matches(tmp_path):
    provider = make_provider(tmp_path)
    provider.create_ticket(make_ticket('SE-1', title='Some ticket'))
    result = provider.search_tickets('zzzznotfound')

    assert result == []


def test_search_tickets_case_insensitive(tmp_path):
    provider = make_provider(tmp_path)
    provider.create_ticket(make_ticket('CI-1', title='Fix Login Bug'))
    result = provider.search_tickets('fix login')

    assert len(result) == 1
    assert result[0].id == 'CI-1'
