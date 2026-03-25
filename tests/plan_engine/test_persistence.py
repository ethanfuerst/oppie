import pytest

from oppie.models.operation import Operation
from oppie.models.plan import Plan, PlanStatus
from oppie.plan import load_plan


def test_save_and_load_plan(home, provider):
    plan = Plan(
        instruction='close bugs',
        operations=[
            Operation('T-1', 'status', 'open', 'done', 'closing'),
        ],
        risks=['some risk'],
        created_at='2026-01-01T00:00:00Z',
        status=PlanStatus.SAVED,
    )

    path = plan.save(home)

    assert path.exists()
    assert path.name == f'plan-{plan.plan_id}.json'

    loaded = load_plan(home, plan.plan_id)

    assert loaded.plan_id == plan.plan_id
    assert loaded.instruction == plan.instruction
    assert len(loaded.operations) == 1
    assert loaded.operations[0].ticket_id == 'T-1'
    assert loaded.status == PlanStatus.SAVED


def test_load_plan_not_found(home, provider):
    with pytest.raises(FileNotFoundError, match='Plan not found'):
        load_plan(home, 'nonexistent')


def test_save_plan_with_parent_plan_id(home, provider):
    plan = Plan(
        instruction='re-close bugs',
        operations=[],
        risks=[],
        created_at='2026-01-01T00:00:00Z',
        status=PlanStatus.SAVED,
        parent_plan_id='parent99',
    )

    plan.save(home)
    loaded = load_plan(home, plan.plan_id)

    assert loaded.parent_plan_id == 'parent99'
