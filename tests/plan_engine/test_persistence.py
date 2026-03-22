import pytest

from oppie.models.operation import Operation
from oppie.models.plan import Plan, PlanStatus
from oppie.plan import PlanEngine


def test_save_and_load_plan(home, provider):
    engine = PlanEngine(home, provider)
    plan = Plan(
        plan_id='abcd1234',
        instruction='close bugs',
        operations=[
            Operation('T-1', 'status', 'open', 'done', 'closing'),
        ],
        risks=['some risk'],
        created_at='2026-01-01T00:00:00Z',
        status=PlanStatus.SAVED,
    )

    path = engine.save_plan(plan)

    assert path.exists()
    assert path.name == 'plan-abcd1234.json'

    loaded = engine.load_plan('abcd1234')

    assert loaded.plan_id == plan.plan_id
    assert loaded.instruction == plan.instruction
    assert len(loaded.operations) == 1
    assert loaded.operations[0].ticket_id == 'T-1'
    assert loaded.status == PlanStatus.SAVED


def test_load_plan_not_found(home, provider):
    engine = PlanEngine(home, provider)

    with pytest.raises(FileNotFoundError, match='Plan not found'):
        engine.load_plan('nonexistent')


def test_save_plan_with_parent_plan_id(home, provider):
    engine = PlanEngine(home, provider)
    plan = Plan(
        plan_id='child123',
        instruction='re-close bugs',
        operations=[],
        risks=[],
        created_at='2026-01-01T00:00:00Z',
        status=PlanStatus.SAVED,
        parent_plan_id='parent99',
    )

    engine.save_plan(plan)
    loaded = engine.load_plan('child123')

    assert loaded.parent_plan_id == 'parent99'
