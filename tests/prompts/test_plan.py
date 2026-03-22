from oppie.models.operation import Operation
from oppie.models.plan import Plan, PlanStatus
from oppie.models.ticket import Ticket, TicketMetadata, TicketSource
from oppie.plan import PlanEngine


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


def test_build_prompt_returns_system_and_user_messages(home, provider):
    engine = PlanEngine(home, provider)
    messages = engine._build_prompt('close all bugs', {}, [], [])

    assert len(messages) == 2
    assert messages[0]['role'] == 'system'
    assert messages[1]['role'] == 'user'


def test_build_prompt_system_message_is_system_prompt(home, provider):
    engine = PlanEngine(home, provider)
    messages = engine._build_prompt('do something', {}, [], [])

    assert messages[0]['content'] == PlanEngine._SYSTEM_PROMPT


def test_build_prompt_includes_instruction(home, provider):
    engine = PlanEngine(home, provider)
    messages = engine._build_prompt('prioritize security work', {}, [], [])

    assert 'prioritize security work' in messages[1]['content']


def test_build_prompt_includes_tickets(home, provider):
    engine = PlanEngine(home, provider)
    ticket = _make_ticket()
    messages = engine._build_prompt('do something', {}, [ticket], [])

    assert 'T-1' in messages[1]['content']
    assert 'Fix bug' in messages[1]['content']


def test_build_prompt_includes_context(home, provider):
    engine = PlanEngine(home, provider)
    context = {'vision': 'Be the best project tracker.'}
    messages = engine._build_prompt('do something', context, [], [])

    assert 'Be the best project tracker.' in messages[1]['content']
    assert 'Vision' in messages[1]['content']


def test_build_prompt_includes_past_plans(home, provider):
    engine = PlanEngine(home, provider)
    plan = Plan(
        plan_id='abc12345',
        instruction='close bugs',
        operations=[
            Operation('T-1', 'status', 'open', 'done', 'closing bug'),
        ],
        risks=[],
        created_at='2026-01-01T00:00:00Z',
        status=PlanStatus.APPLIED,
    )
    messages = engine._build_prompt('close all bugs', {}, [], [plan])

    assert 'abc12345' in messages[1]['content']
    assert 'close bugs' in messages[1]['content']


def test_format_tickets_empty():
    assert PlanEngine._format_tickets([]) == '(no tickets)'


def test_format_tickets_includes_fields():
    ticket = _make_ticket(ticket_id='T-99', title='Deploy fix', status='in_progress')
    result = PlanEngine._format_tickets([ticket])

    assert 'T-99' in result
    assert 'Deploy fix' in result
    assert 'in_progress' in result


def test_format_past_plans_empty():
    assert PlanEngine._format_past_plans([]) == '(no similar past plans)'


def test_format_context_empty():
    assert PlanEngine._format_context({}) == ''


def test_format_context_multiple_docs():
    context = {'vision': 'v content', 'roadmap': 'r content'}
    result = PlanEngine._format_context(context)

    assert 'Vision' in result
    assert 'v content' in result
    assert 'Roadmap' in result
    assert 'r content' in result
