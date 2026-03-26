import json

from oppie.models.operation import Operation
from oppie.models.plan import Plan, PlanStatus
from oppie.plan import check_apply
from tests.apply_engine.conftest import make_and_save_plan
from tests.helpers import make_ticket, write_ticket


def test_check_apply_clean_plan(home, provider):
    ticket = make_ticket('T-1', status='open')
    write_ticket(home, ticket)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = make_and_save_plan(home, ops)

    result = check_apply(provider, plan.plan_id)

    assert result.can_apply is True
    assert result.integrity_ok is True
    assert result.already_applied is False
    assert not result.drift.has_any
    assert result.capability_errors == []


def test_check_apply_integrity_failure(home, provider):
    ticket = make_ticket('T-1', status='open')
    write_ticket(home, ticket)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    make_and_save_plan(home, ops)

    # Tamper with the plan file: change plan_id and rename file to match
    plan_id = Plan.compute_id(ops)
    plan_path = home / 'artifacts' / 'plans' / f'plan-{plan_id}.json'
    data = json.loads(plan_path.read_text())
    data['plan_id'] = 'tampered'
    tampered_path = home / 'artifacts' / 'plans' / 'plan-tampered.json'
    tampered_path.write_text(json.dumps(data, indent=2) + '\n')

    result = check_apply(provider, 'tampered')

    assert result.integrity_ok is False
    assert result.can_apply is False


def test_check_apply_already_applied(home, provider):
    ticket = make_ticket('T-1', status='open')
    write_ticket(home, ticket)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = make_and_save_plan(home, ops, status=PlanStatus.APPLIED)

    result = check_apply(provider, plan.plan_id)

    assert result.already_applied is True
    assert result.can_apply is False


def test_check_apply_with_critical_drift(home, provider):
    # Ticket status changed since plan was created
    ticket = make_ticket('T-1', status='in_progress')
    write_ticket(home, ticket)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = make_and_save_plan(home, ops)

    result = check_apply(provider, plan.plan_id)

    assert result.drift.has_critical is True
    assert result.can_apply is False


def test_check_apply_with_capability_errors(home, provider):
    ticket = make_ticket('T-1', status='open')
    write_ticket(home, ticket)
    # Use a field the provider doesn't support
    ops = [Operation('T-1', 'nonexistent_field', None, 'val', 'test')]
    plan = make_and_save_plan(home, ops)

    result = check_apply(provider, plan.plan_id)

    assert len(result.capability_errors) > 0
    assert result.can_apply is False
