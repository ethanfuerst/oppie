import json

from oppie.models.plan import Plan, PlanStatus
from oppie.plan import PlanEngine


def test_find_similar_plans_matches_by_keyword_overlap(home, provider):
    engine = PlanEngine(home, provider)
    plan = Plan(
        plan_id='aaa11111',
        instruction='close all security bugs',
        operations=[],
        risks=[],
        created_at='2026-01-01T00:00:00Z',
        status=PlanStatus.SAVED,
    )
    engine.save_plan(plan)

    result = engine._find_similar_plans('close security tickets')

    assert len(result) == 1
    assert result[0].plan_id == 'aaa11111'


def test_find_similar_plans_returns_empty_for_no_overlap(home, provider):
    engine = PlanEngine(home, provider)
    plan = Plan(
        plan_id='bbb22222',
        instruction='deploy infrastructure',
        operations=[],
        risks=[],
        created_at='2026-01-01T00:00:00Z',
        status=PlanStatus.SAVED,
    )
    engine.save_plan(plan)

    result = engine._find_similar_plans('close all bugs')

    assert result == []


def test_find_similar_plans_respects_limit(home, provider):
    engine = PlanEngine(home, provider)
    for i in range(5):
        plan = Plan(
            plan_id=f'plan{i:04d}',
            instruction=f'close bug number {i}',
            operations=[],
            risks=[],
            created_at='2026-01-01T00:00:00Z',
            status=PlanStatus.SAVED,
        )
        engine.save_plan(plan)

    result = engine._find_similar_plans('close bug', limit=2)

    assert len(result) == 2


def test_find_similar_plans_rebuilds_index_when_missing(home, provider):
    engine = PlanEngine(home, provider)
    plan = Plan(
        plan_id='ccc33333',
        instruction='close all bugs',
        operations=[],
        risks=[],
        created_at='2026-01-01T00:00:00Z',
        status=PlanStatus.SAVED,
    )
    # Write plan JSON directly without index
    plan_path = home / 'artifacts' / 'plans' / 'plan-ccc33333.json'
    plan_path.write_text(json.dumps(plan.to_dict(), indent=2))

    result = engine._find_similar_plans('close bugs')

    assert len(result) == 1
    assert result[0].plan_id == 'ccc33333'
    # Verify index was rebuilt
    assert (home / 'artifacts' / 'plans' / PlanEngine.PLAN_INDEX_FILENAME).exists()


def test_find_similar_plans_skips_malformed_index_entries(home, provider):
    engine = PlanEngine(home, provider)
    plan = Plan(
        plan_id='ddd44444',
        instruction='close bugs',
        operations=[],
        risks=[],
        created_at='2026-01-01T00:00:00Z',
        status=PlanStatus.SAVED,
    )
    engine.save_plan(plan)
    # Append a malformed line to the index
    index_path = home / 'artifacts' / 'plans' / PlanEngine.PLAN_INDEX_FILENAME
    with open(index_path, 'a') as f:
        f.write('not valid json\n')

    result = engine._find_similar_plans('close bugs')

    assert len(result) == 1
