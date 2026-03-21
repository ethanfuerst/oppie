import json

import pytest

from oppie.models.apply import OperationStatus
from oppie.models.drift import DriftResolution
from oppie.models.operation import Operation
from oppie.models.plan import Plan, PlanStatus
from oppie.plan import PlanEngine
from oppie.providers.local import LocalProvider
from oppie.run_log import RunLog
from tests.helpers import make_ticket, setup_instance, write_ticket


def _make_and_save_plan(
    engine, operations, status=PlanStatus.SAVED, ticket_snapshots=None
):
    """Create a plan with correct plan_id and save it."""
    plan_id = Plan.compute_id(operations)
    plan = Plan(
        plan_id=plan_id,
        instruction='test instruction',
        operations=operations,
        risks=[],
        created_at='2026-01-01T00:00:00Z',
        status=status,
        ticket_snapshots=ticket_snapshots,
    )
    engine.save_plan(plan)
    return plan


def _make_engine(home):
    provider = LocalProvider(home)
    return PlanEngine(home, provider), provider


# --- check_apply ---


def test_check_apply_clean_plan(tmp_path):
    home = setup_instance(tmp_path)
    ticket = make_ticket('T-1', status='open')
    write_ticket(home, ticket)
    engine, provider = _make_engine(home)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = _make_and_save_plan(engine, ops)

    result = engine.check_apply(plan.plan_id)
    provider.close()

    assert result.can_apply is True
    assert result.integrity_ok is True
    assert result.already_applied is False
    assert not result.drift.has_any
    assert result.capability_errors == []


def test_check_apply_integrity_failure(tmp_path):
    home = setup_instance(tmp_path)
    ticket = make_ticket('T-1', status='open')
    write_ticket(home, ticket)
    engine, provider = _make_engine(home)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    _make_and_save_plan(engine, ops)

    # Tamper with the plan file: change plan_id and rename file to match
    plan_id = Plan.compute_id(ops)
    plan_path = home / 'artifacts' / 'plans' / f'plan-{plan_id}.json'
    data = json.loads(plan_path.read_text())
    data['plan_id'] = 'tampered'
    tampered_path = home / 'artifacts' / 'plans' / 'plan-tampered.json'
    tampered_path.write_text(json.dumps(data, indent=2) + '\n')

    result = engine.check_apply('tampered')
    provider.close()

    assert result.integrity_ok is False
    assert result.can_apply is False


def test_check_apply_already_applied(tmp_path):
    home = setup_instance(tmp_path)
    ticket = make_ticket('T-1', status='open')
    write_ticket(home, ticket)
    engine, provider = _make_engine(home)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = _make_and_save_plan(engine, ops, status=PlanStatus.APPLIED)

    result = engine.check_apply(plan.plan_id)
    provider.close()

    assert result.already_applied is True
    assert result.can_apply is False


def test_check_apply_with_critical_drift(tmp_path):
    home = setup_instance(tmp_path)
    # Ticket status changed since plan was created
    ticket = make_ticket('T-1', status='in_progress')
    write_ticket(home, ticket)
    engine, provider = _make_engine(home)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = _make_and_save_plan(engine, ops)

    result = engine.check_apply(plan.plan_id)
    provider.close()

    assert result.drift.has_critical is True
    assert result.can_apply is False


def test_check_apply_with_capability_errors(tmp_path):
    home = setup_instance(tmp_path)
    ticket = make_ticket('T-1', status='open')
    write_ticket(home, ticket)
    engine, provider = _make_engine(home)
    # Use a field the provider doesn't support
    ops = [Operation('T-1', 'nonexistent_field', None, 'val', 'test')]
    plan = _make_and_save_plan(engine, ops)

    result = engine.check_apply(plan.plan_id)
    provider.close()

    assert len(result.capability_errors) > 0
    assert result.can_apply is False


# --- execute_apply ---


def test_execute_apply_success(tmp_path):
    home = setup_instance(tmp_path)
    ticket = make_ticket('T-1', status='open')
    write_ticket(home, ticket)
    engine, provider = _make_engine(home)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = _make_and_save_plan(engine, ops)

    result = engine.execute_apply(plan.plan_id)
    provider.close()

    assert len(result.results) == 1
    assert result.results[0].status == OperationStatus.OK
    assert result.plan_id == plan.plan_id

    # Verify plan marked as applied
    engine2, provider2 = _make_engine(home)
    loaded = engine2.load_plan(plan.plan_id)
    provider2.close()

    assert loaded.status == PlanStatus.APPLIED

    # Verify ticket was updated
    ticket_path = home / 'tickets' / 'T-1.json'
    ticket_data = json.loads(ticket_path.read_text())
    assert ticket_data['status'] == 'done'


def test_execute_apply_partial_failure(tmp_path):
    home = setup_instance(tmp_path)
    t1 = make_ticket('T-1', status='open')
    t2 = make_ticket('T-2', status='open')
    t3 = make_ticket('T-3', status='open')
    write_ticket(home, t1)
    write_ticket(home, t2)
    write_ticket(home, t3)
    engine, provider = _make_engine(home)
    ops = [
        Operation('T-1', 'status', 'open', 'done', 'closing'),
        Operation('T-2', 'id', 'T-2', 'T-NEW', 'rename'),  # Will fail (can't update id)
        Operation('T-3', 'status', 'open', 'done', 'closing'),
    ]
    plan = _make_and_save_plan(engine, ops)

    result = engine.execute_apply(plan.plan_id)
    provider.close()

    assert len(result.results) == 3
    assert result.results[0].status == OperationStatus.OK
    assert result.results[1].status == OperationStatus.FAILED
    assert result.results[1].error is not None
    assert result.results[2].status == OperationStatus.SKIPPED


def test_execute_apply_force_skips_drift(tmp_path):
    home = setup_instance(tmp_path)
    # Ticket drifted
    ticket = make_ticket('T-1', status='in_progress')
    write_ticket(home, ticket)
    engine, provider = _make_engine(home)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = _make_and_save_plan(engine, ops)

    result = engine.execute_apply(plan.plan_id, force=True)
    provider.close()

    assert len(result.results) == 1
    assert result.results[0].status == OperationStatus.OK

    # Verify ticket was updated to plan's after_value
    ticket_path = home / 'tickets' / 'T-1.json'
    ticket_data = json.loads(ticket_path.read_text())
    assert ticket_data['status'] == 'done'


def test_execute_apply_integrity_failure_raises(tmp_path):
    home = setup_instance(tmp_path)
    ticket = make_ticket('T-1', status='open')
    write_ticket(home, ticket)
    engine, provider = _make_engine(home)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = _make_and_save_plan(engine, ops)

    # Tamper with the plan file: change plan_id and rename file to match
    plan_path = home / 'artifacts' / 'plans' / f'plan-{plan.plan_id}.json'
    data = json.loads(plan_path.read_text())
    data['plan_id'] = 'tampered'
    tampered_path = home / 'artifacts' / 'plans' / 'plan-tampered.json'
    tampered_path.write_text(json.dumps(data, indent=2) + '\n')

    with pytest.raises(ValueError, match='Plan integrity check failed'):
        engine.execute_apply('tampered')
    provider.close()


def test_execute_apply_already_applied_raises(tmp_path):
    home = setup_instance(tmp_path)
    ticket = make_ticket('T-1', status='open')
    write_ticket(home, ticket)
    engine, provider = _make_engine(home)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = _make_and_save_plan(engine, ops, status=PlanStatus.APPLIED)

    with pytest.raises(ValueError, match='has already been applied'):
        engine.execute_apply(plan.plan_id)
    provider.close()


def test_execute_apply_deleted_ticket_raises(tmp_path):
    home = setup_instance(tmp_path)
    # Don't write any ticket -- it's "deleted"
    engine, provider = _make_engine(home)
    ops = [Operation('T-GONE', 'status', 'open', 'done', 'closing')]
    plan = _make_and_save_plan(engine, ops)

    with pytest.raises(ValueError, match='tickets deleted'):
        engine.execute_apply(plan.plan_id)
    provider.close()


def test_execute_apply_critical_drift_no_resolutions_raises(tmp_path):
    home = setup_instance(tmp_path)
    ticket = make_ticket('T-1', status='in_progress')
    write_ticket(home, ticket)
    engine, provider = _make_engine(home)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = _make_and_save_plan(engine, ops)

    with pytest.raises(ValueError, match='Critical drift detected'):
        engine.execute_apply(plan.plan_id)
    provider.close()


def test_execute_apply_with_resolutions_skip(tmp_path):
    home = setup_instance(tmp_path)
    ticket = make_ticket('T-1', status='in_progress')
    write_ticket(home, ticket)
    engine, provider = _make_engine(home)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = _make_and_save_plan(engine, ops)

    resolutions = {('T-1', 'status'): DriftResolution.SKIP_OPERATION}
    result = engine.execute_apply(plan.plan_id, resolutions=resolutions)
    provider.close()

    assert len(result.results) == 1
    assert result.results[0].status == OperationStatus.SKIPPED
    assert result.results[0].error == 'Skipped via drift resolution'


def test_execute_apply_with_resolutions_keep_plan(tmp_path):
    home = setup_instance(tmp_path)
    ticket = make_ticket('T-1', status='in_progress')
    write_ticket(home, ticket)
    engine, provider = _make_engine(home)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = _make_and_save_plan(engine, ops)

    resolutions = {('T-1', 'status'): DriftResolution.KEEP_PLAN_VALUE}
    result = engine.execute_apply(plan.plan_id, resolutions=resolutions)
    provider.close()

    assert len(result.results) == 1
    assert result.results[0].status == OperationStatus.OK

    # Verify ticket was updated to plan's after_value
    ticket_path = home / 'tickets' / 'T-1.json'
    ticket_data = json.loads(ticket_path.read_text())
    assert ticket_data['status'] == 'done'


def test_execute_apply_with_resolutions_keep_current(tmp_path):
    home = setup_instance(tmp_path)
    ticket = make_ticket('T-1', status='in_progress')
    write_ticket(home, ticket)
    engine, provider = _make_engine(home)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = _make_and_save_plan(engine, ops)

    resolutions = {('T-1', 'status'): DriftResolution.KEEP_CURRENT_VALUE}
    result = engine.execute_apply(plan.plan_id, resolutions=resolutions)
    provider.close()

    assert len(result.results) == 1
    assert result.results[0].status == OperationStatus.SKIPPED

    # Verify ticket was NOT updated
    ticket_path = home / 'tickets' / 'T-1.json'
    ticket_data = json.loads(ticket_path.read_text())
    assert ticket_data['status'] == 'in_progress'


def test_execute_apply_writes_artifact(tmp_path):
    home = setup_instance(tmp_path)
    ticket = make_ticket('T-1', status='open')
    write_ticket(home, ticket)
    engine, provider = _make_engine(home)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = _make_and_save_plan(engine, ops)

    engine.execute_apply(plan.plan_id)
    provider.close()

    applies_dir = home / 'artifacts' / 'applies'
    artifact_files = list(applies_dir.glob('apply-*.json'))

    assert len(artifact_files) == 1
    content = artifact_files[0].read_text()
    assert plan.plan_id in content
    assert 'test instruction' in content


def test_execute_apply_writes_run_log(tmp_path):
    home = setup_instance(tmp_path)
    ticket = make_ticket('T-1', status='open')
    write_ticket(home, ticket)
    engine, provider = _make_engine(home)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = _make_and_save_plan(engine, ops)

    result = engine.execute_apply(plan.plan_id)
    provider.close()

    run_log = RunLog(home)
    entries = run_log.query(command_type='apply')

    assert len(entries) == 1
    assert entries[0].plan_id == plan.plan_id
    assert entries[0].apply_id == result.apply_id
    assert entries[0].command == 'apply'
