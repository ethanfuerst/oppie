from oppie.models.operation import Operation
from oppie.models.plan import Plan, PlanStatus
from oppie.models.ticket import Ticket, TicketMetadata, TicketSource
from oppie.plan.engine import (
    _SYSTEM_PROMPT,
    _build_prompt,
    _format_context,
    _format_past_plans,
    _format_tickets,
)


def _make_ticket(ticket_id='T-1', title='Fix bug', status='open', priority='high'):
    return Ticket(
        id=ticket_id,
        title=title,
        status=status,
        priority=priority,
        owner='alice',
        labels=['bug'],
        created_at='2026-01-01T00:00:00Z',
        updated_at='2026-01-01T00:00:00Z',
        project='proj',
        description='A bug',
        metadata=TicketMetadata(source=TicketSource.LOCAL),
    )


def test_build_prompt_returns_system_and_user_messages():
    messages = _build_prompt('close all bugs', {}, [], [])

    assert len(messages) == 2
    assert messages[0]['role'] == 'system'
    assert messages[1]['role'] == 'user'


def test_build_prompt_system_message_is_system_prompt():
    messages = _build_prompt('do something', {}, [], [])

    assert messages[0]['content'] == _SYSTEM_PROMPT


def test_build_prompt_includes_instruction():
    messages = _build_prompt('prioritize security work', {}, [], [])

    assert 'prioritize security work' in messages[1]['content']


def test_build_prompt_includes_tickets():
    ticket = _make_ticket()
    messages = _build_prompt('do something', {}, [ticket], [])

    assert 'T-1' in messages[1]['content']
    assert 'Fix bug' in messages[1]['content']


def test_build_prompt_includes_context():
    context = {'vision': 'Be the best project tracker.'}
    messages = _build_prompt('do something', context, [], [])

    assert 'Be the best project tracker.' in messages[1]['content']
    assert 'Vision' in messages[1]['content']


def test_build_prompt_includes_past_plans():
    plan = Plan(
        instruction='close bugs',
        operations=[
            Operation('T-1', 'status', 'open', 'done', 'closing bug'),
        ],
        risks=[],
        created_at='2026-01-01T00:00:00Z',
        status=PlanStatus.APPLIED,
    )
    messages = _build_prompt('close all bugs', {}, [], [plan])

    assert plan.plan_id in messages[1]['content']
    assert 'close bugs' in messages[1]['content']


def test_format_tickets_empty():
    assert _format_tickets([]) == '(no tickets)'


def test_format_tickets_includes_fields():
    ticket = _make_ticket(ticket_id='T-99', title='Deploy fix', status='in_progress')
    result = _format_tickets([ticket])

    assert 'T-99' in result
    assert 'Deploy fix' in result
    assert 'in_progress' in result


def test_format_past_plans_empty():
    assert _format_past_plans([]) == '(no similar past plans)'


def test_format_context_empty():
    assert _format_context({}) == ''


def test_format_context_multiple_docs():
    context = {'vision': 'v content', 'roadmap': 'r content'}
    result = _format_context(context)

    assert 'Vision' in result
    assert 'v content' in result
    assert 'Roadmap' in result
    assert 'r content' in result
