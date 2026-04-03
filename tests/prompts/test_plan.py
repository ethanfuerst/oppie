from oppie.models.operation import Operation
from oppie.models.plan import Plan, PlanStatus
from oppie.models.ticket import Ticket, TicketMetadata, TicketSource
from oppie.prompts.builder import PromptMode, build_system_prompt, flatten_system_prompt
from oppie.prompts.formatting import format_context_for_llm as _format_context
from oppie.prompts.formatting import format_past_plans as _format_past_plans
from oppie.prompts.formatting import format_tickets_for_llm as _format_tickets
from oppie.prompts.text.plan import PLAN_BASE_PROMPT
from tests.helpers import setup_instance


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


def test_build_plan_prompt_includes_base(tmp_path):
    home = setup_instance(tmp_path)

    parts = build_system_prompt(mode=PromptMode.PLAN, home=home)

    flat = flatten_system_prompt(parts)
    assert PLAN_BASE_PROMPT in flat


def test_build_plan_prompt_includes_instruction_context(tmp_path):
    home = setup_instance(tmp_path)

    parts = build_system_prompt(mode=PromptMode.PLAN, home=home)

    flat = flatten_system_prompt(parts)
    assert 'Current date' in flat


def test_build_prompt_includes_context(tmp_path):
    home = setup_instance(tmp_path)
    (home / 'context' / 'vision.md').write_text('Be the best project tracker.')

    parts = build_system_prompt(mode=PromptMode.PLAN, home=home)

    flat = flatten_system_prompt(parts)
    assert 'Be the best project tracker.' in flat
    assert 'Vision' in flat


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
    past_plans_text = _format_past_plans([plan])

    assert plan.plan_id in past_plans_text
    assert 'close bugs' in past_plans_text


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
