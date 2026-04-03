from oppie.prompt.helpers import (
    format_context_for_llm,
    format_tickets_for_llm,
    load_context,
)
from tests.helpers import make_ticket


def test_format_tickets_for_llm_empty():
    assert format_tickets_for_llm([]) == '(no tickets)'


def test_format_tickets_for_llm_single():
    ticket = make_ticket(ticket_id='T-1', status='open', priority='high')

    result = format_tickets_for_llm([ticket])

    assert 'T-1' in result
    assert 'Ticket T-1' in result
    assert 'open' in result


def test_format_context_for_llm_empty():
    assert format_context_for_llm({}) == ''


def test_format_context_for_llm_single():
    result = format_context_for_llm({'vision': 'Ship fast.'})

    assert '## Vision' in result
    assert 'Ship fast.' in result


def test_load_context_no_dir(tmp_path):
    result = load_context(tmp_path)

    assert result == {}


def test_load_context_with_files(tmp_path):
    ctx_dir = tmp_path / 'context'
    ctx_dir.mkdir()
    (ctx_dir / 'vision.md').write_text('Ship fast.')
    (ctx_dir / 'roadmap.md').write_text('Q1 goals.')

    result = load_context(tmp_path)

    assert result['vision'] == 'Ship fast.'
    assert result['roadmap'] == 'Q1 goals.'
