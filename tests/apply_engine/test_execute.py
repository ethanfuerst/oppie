import json

import pytest

from oppie.models.apply import OperationStatus
from oppie.models.drift import DriftResolution
from oppie.models.operation import Operation
from oppie.models.plan import PlanStatus
from oppie.plan import PlanEngine
from oppie.providers.local import LocalProvider
from oppie.run_log import RunLog
from tests.apply_engine.conftest import make_and_save_plan
from tests.helpers import make_ticket, write_ticket


def test_execute_apply_success(home, provider):
    ticket = make_ticket('T-1', status='open')
    write_ticket(home, ticket)
    engine = PlanEngine(home, provider)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = make_and_save_plan(engine, ops)

    result = engine.execute_apply(plan.plan_id)

    assert len(result.results) == 1
    assert result.results[0].status == OperationStatus.OK
    assert result.plan_id == plan.plan_id

    # Verify plan marked as applied with a fresh engine
    provider2 = LocalProvider(home)
    engine2 = PlanEngine(home, provider2)
    loaded = engine2.load_plan(plan.plan_id)
    provider2.close()

    assert loaded.status == PlanStatus.APPLIED

    # Verify ticket was updated
    ticket_path = home / 'tickets' / 'T-1.json'
    ticket_data = json.loads(ticket_path.read_text())
    assert ticket_data['status'] == 'done'


def test_execute_apply_partial_failure(home, provider):
    t1 = make_ticket('T-1', status='open')
    t2 = make_ticket('T-2', status='open')
    t3 = make_ticket('T-3', status='open')
    write_ticket(home, t1)
    write_ticket(home, t2)
    write_ticket(home, t3)
    engine = PlanEngine(home, provider)
    ops = [
        Operation('T-1', 'status', 'open', 'done', 'closing'),
        Operation('T-2', 'id', 'T-2', 'T-NEW', 'rename'),  # Will fail (can't update id)
        Operation('T-3', 'status', 'open', 'done', 'closing'),
    ]
    plan = make_and_save_plan(engine, ops)

    result = engine.execute_apply(plan.plan_id)

    assert len(result.results) == 3
    assert result.results[0].status == OperationStatus.OK
    assert result.results[1].status == OperationStatus.FAILED
    assert result.results[1].error is not None
    assert result.results[2].status == OperationStatus.SKIPPED


def test_execute_apply_force_skips_drift(home, provider):
    # Ticket drifted
    ticket = make_ticket('T-1', status='in_progress')
    write_ticket(home, ticket)
    engine = PlanEngine(home, provider)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = make_and_save_plan(engine, ops)

    result = engine.execute_apply(plan.plan_id, force=True)

    assert len(result.results) == 1
    assert result.results[0].status == OperationStatus.OK

    # Verify ticket was updated to plan's after_value
    ticket_path = home / 'tickets' / 'T-1.json'
    ticket_data = json.loads(ticket_path.read_text())
    assert ticket_data['status'] == 'done'


def test_execute_apply_integrity_failure_raises(home, provider):
    ticket = make_ticket('T-1', status='open')
    write_ticket(home, ticket)
    engine = PlanEngine(home, provider)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = make_and_save_plan(engine, ops)

    # Tamper with the plan file: change plan_id and rename file to match
    plan_path = home / 'artifacts' / 'plans' / f'plan-{plan.plan_id}.json'
    data = json.loads(plan_path.read_text())
    data['plan_id'] = 'tampered'
    tampered_path = home / 'artifacts' / 'plans' / 'plan-tampered.json'
    tampered_path.write_text(json.dumps(data, indent=2) + '\n')

    with pytest.raises(ValueError, match='Plan integrity check failed'):
        engine.execute_apply('tampered')


def test_execute_apply_already_applied_raises(home, provider):
    ticket = make_ticket('T-1', status='open')
    write_ticket(home, ticket)
    engine = PlanEngine(home, provider)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = make_and_save_plan(engine, ops, status=PlanStatus.APPLIED)

    with pytest.raises(ValueError, match='has already been applied'):
        engine.execute_apply(plan.plan_id)


def test_execute_apply_deleted_ticket_raises(home, provider):
    # Don't write any ticket -- it's "deleted"
    engine = PlanEngine(home, provider)
    ops = [Operation('T-GONE', 'status', 'open', 'done', 'closing')]
    plan = make_and_save_plan(engine, ops)

    with pytest.raises(ValueError, match='tickets deleted'):
        engine.execute_apply(plan.plan_id)


def test_execute_apply_critical_drift_no_resolutions_raises(home, provider):
    ticket = make_ticket('T-1', status='in_progress')
    write_ticket(home, ticket)
    engine = PlanEngine(home, provider)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = make_and_save_plan(engine, ops)

    with pytest.raises(ValueError, match='Critical drift detected'):
        engine.execute_apply(plan.plan_id)


def test_execute_apply_with_resolutions_skip(home, provider):
    ticket = make_ticket('T-1', status='in_progress')
    write_ticket(home, ticket)
    engine = PlanEngine(home, provider)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = make_and_save_plan(engine, ops)

    resolutions = {('T-1', 'status'): DriftResolution.SKIP_OPERATION}
    result = engine.execute_apply(plan.plan_id, resolutions=resolutions)

    assert len(result.results) == 1
    assert result.results[0].status == OperationStatus.SKIPPED
    assert result.results[0].error == 'Skipped via drift resolution'


def test_execute_apply_with_resolutions_keep_plan(home, provider):
    ticket = make_ticket('T-1', status='in_progress')
    write_ticket(home, ticket)
    engine = PlanEngine(home, provider)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = make_and_save_plan(engine, ops)

    resolutions = {('T-1', 'status'): DriftResolution.KEEP_PLAN_VALUE}
    result = engine.execute_apply(plan.plan_id, resolutions=resolutions)

    assert len(result.results) == 1
    assert result.results[0].status == OperationStatus.OK

    # Verify ticket was updated to plan's after_value
    ticket_path = home / 'tickets' / 'T-1.json'
    ticket_data = json.loads(ticket_path.read_text())
    assert ticket_data['status'] == 'done'


def test_execute_apply_with_resolutions_keep_current(home, provider):
    ticket = make_ticket('T-1', status='in_progress')
    write_ticket(home, ticket)
    engine = PlanEngine(home, provider)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = make_and_save_plan(engine, ops)

    resolutions = {('T-1', 'status'): DriftResolution.KEEP_CURRENT_VALUE}
    result = engine.execute_apply(plan.plan_id, resolutions=resolutions)

    assert len(result.results) == 1
    assert result.results[0].status == OperationStatus.SKIPPED

    # Verify ticket was NOT updated
    ticket_path = home / 'tickets' / 'T-1.json'
    ticket_data = json.loads(ticket_path.read_text())
    assert ticket_data['status'] == 'in_progress'


def test_execute_apply_writes_artifact(home, provider):
    ticket = make_ticket('T-1', status='open')
    write_ticket(home, ticket)
    engine = PlanEngine(home, provider)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = make_and_save_plan(engine, ops)

    engine.execute_apply(plan.plan_id)

    applies_dir = home / 'artifacts' / 'applies'
    artifact_files = list(applies_dir.glob('apply-*.json'))

    assert len(artifact_files) == 1
    content = artifact_files[0].read_text()
    assert plan.plan_id in content
    assert 'test instruction' in content


def test_execute_apply_writes_run_log(home, provider):
    ticket = make_ticket('T-1', status='open')
    write_ticket(home, ticket)
    engine = PlanEngine(home, provider)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = make_and_save_plan(engine, ops)

    result = engine.execute_apply(plan.plan_id)

    run_log = RunLog(home)
    entries = run_log.query(command_type='apply')

    assert len(entries) == 1
    assert entries[0].plan_id == plan.plan_id
    assert entries[0].apply_id == result.apply_id
    assert entries[0].command == 'apply'
