import json

from oppie.models.plan import PLAN_INDEX_FILENAME, Plan, PlanStatus
from oppie.plan.engine import _find_similar_plans


def test_find_similar_plans_matches_by_keyword_overlap(home, provider):
    plan = Plan(
        instruction='close all security bugs',
        operations=[],
        risks=[],
        created_at='2026-01-01T00:00:00Z',
        status=PlanStatus.SAVED,
    )
    plan.save(home)

    result = _find_similar_plans(home, 'close security tickets')

    assert len(result) == 1
    assert result[0].plan_id == plan.plan_id


def test_find_similar_plans_returns_empty_for_no_overlap(home, provider):
    plan = Plan(
        instruction='deploy infrastructure',
        operations=[],
        risks=[],
        created_at='2026-01-01T00:00:00Z',
        status=PlanStatus.SAVED,
    )
    plan.save(home)

    result = _find_similar_plans(home, 'close all bugs')

    assert result == []


def test_find_similar_plans_respects_limit(home, provider):
    for i in range(5):
        plan = Plan(
            instruction=f'close bug number {i}',
            operations=[],
            risks=[],
            created_at='2026-01-01T00:00:00Z',
            status=PlanStatus.SAVED,
        )
        plan.save(home)

    result = _find_similar_plans(home, 'close bug', limit=2)

    assert len(result) == 2


def test_find_similar_plans_rebuilds_index_when_missing(home, provider):
    plan = Plan(
        instruction='close all bugs',
        operations=[],
        risks=[],
        created_at='2026-01-01T00:00:00Z',
        status=PlanStatus.SAVED,
    )
    # Write plan JSON directly without index
    plans_dir = home / 'artifacts' / 'plans'
    plans_dir.mkdir(parents=True, exist_ok=True)
    plan_path = plans_dir / f'plan-{plan.plan_id}.json'
    plan_path.write_text(json.dumps(plan.to_dict(), indent=2))

    result = _find_similar_plans(home, 'close bugs')

    assert len(result) == 1
    assert result[0].plan_id == plan.plan_id
    # Verify index was rebuilt
    assert (plans_dir / PLAN_INDEX_FILENAME).exists()


def test_find_similar_plans_empty_instruction(home, provider):
    plan = Plan(
        instruction='close bugs',
        operations=[],
        risks=[],
        created_at='2026-01-01T00:00:00Z',
        status=PlanStatus.SAVED,
    )
    plan.save(home)

    result = _find_similar_plans(home, '')

    assert result == []


def test_find_similar_plans_skips_deleted_plan_file(home, provider):
    plan = Plan(
        instruction='close bugs',
        operations=[],
        risks=[],
        created_at='2026-01-01T00:00:00Z',
        status=PlanStatus.SAVED,
    )
    plan.save(home)
    # Delete the plan file but leave the index entry
    plan_path = home / 'artifacts' / 'plans' / f'plan-{plan.plan_id}.json'
    plan_path.unlink()

    result = _find_similar_plans(home, 'close bugs')

    assert result == []


def test_find_similar_plans_no_plans_dir(home, provider):
    # Remove the plans dir entirely
    plans_dir = home / 'artifacts' / 'plans'
    plans_dir.rmdir()

    result = _find_similar_plans(home, 'close bugs')

    assert result == []


def test_find_similar_plans_skips_blank_index_lines(home, provider):
    plan = Plan(
        instruction='close bugs',
        operations=[],
        risks=[],
        created_at='2026-01-01T00:00:00Z',
        status=PlanStatus.SAVED,
    )
    plan.save(home)
    # Insert blank lines into the index
    index_path = home / 'artifacts' / 'plans' / PLAN_INDEX_FILENAME
    content = index_path.read_text()
    index_path.write_text('\n\n' + content + '\n\n')

    result = _find_similar_plans(home, 'close bugs')

    assert len(result) == 1


def test_find_similar_plans_skips_malformed_index_entries(home, provider):
    plan = Plan(
        instruction='close bugs',
        operations=[],
        risks=[],
        created_at='2026-01-01T00:00:00Z',
        status=PlanStatus.SAVED,
    )
    plan.save(home)
    # Append a malformed line to the index
    index_path = home / 'artifacts' / 'plans' / PLAN_INDEX_FILENAME
    with open(index_path, 'a') as f:
        f.write('not valid json\n')

    result = _find_similar_plans(home, 'close bugs')

    assert len(result) == 1


def test_rebuild_plan_index_skips_corrupt_plan_files(home, provider):
    # Save a valid plan
    plan = Plan(
        instruction='close bugs',
        operations=[],
        risks=[],
        created_at='2026-01-01T00:00:00Z',
        status=PlanStatus.SAVED,
    )
    plan.save(home)
    # Write a corrupt plan file
    plans_dir = home / 'artifacts' / 'plans'
    (plans_dir / 'plan-corrupt.json').write_text('not json at all')
    # Delete the index to force rebuild
    (plans_dir / PLAN_INDEX_FILENAME).unlink()

    result = _find_similar_plans(home, 'close bugs')

    assert len(result) == 1
    assert result[0].plan_id == plan.plan_id
