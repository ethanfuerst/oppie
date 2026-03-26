from oppie.models.plan import PlanStatus
from oppie.plan.engine import _generate_fallback
from tests.helpers import make_ticket, write_ticket


def test_fallback_generates_status_operations(home, provider):
    ticket = make_ticket(ticket_id='T-1', status='open')
    write_ticket(home, ticket)

    plan = _generate_fallback(provider, 'close all tickets')

    assert plan.status == PlanStatus.SAVED
    assert len(plan.operations) == 1
    assert plan.operations[0].field == 'status'
    assert plan.operations[0].after_value == 'done'
    assert plan.operations[0].before_value == 'open'


def test_fallback_generates_priority_operations(home, provider):
    ticket = make_ticket(ticket_id='T-2', priority='low')
    write_ticket(home, ticket)

    plan = _generate_fallback(provider, 'prioritize these tickets')

    assert len(plan.operations) == 1
    assert plan.operations[0].field == 'priority'
    assert plan.operations[0].after_value == 'high'


def test_fallback_skips_tickets_already_in_target_state(home, provider):
    ticket = make_ticket(ticket_id='T-3', status='done')
    write_ticket(home, ticket)

    plan = _generate_fallback(provider, 'close everything')

    assert plan.operations == []


def test_fallback_filters_by_label_keywords(home, provider):
    t1 = make_ticket(ticket_id='T-1', status='open', labels=['security'])
    t2 = make_ticket(ticket_id='T-2', status='open', labels=['docs'])
    write_ticket(home, t1)
    write_ticket(home, t2)

    plan = _generate_fallback(provider, 'close security tickets')

    ticket_ids = [op.ticket_id for op in plan.operations]

    assert 'T-1' in ticket_ids
    assert 'T-2' not in ticket_ids


def test_fallback_no_matching_keywords(home, provider):
    ticket = make_ticket(ticket_id='T-1', status='open')
    write_ticket(home, ticket)

    plan = _generate_fallback(provider, 'do something vague')

    assert plan.operations == []
    assert 'without LLM' in plan.risks[0]


def test_fallback_includes_no_llm_risk(home, provider):
    plan = _generate_fallback(provider, 'close things')

    assert any('without LLM' in r for r in plan.risks)
