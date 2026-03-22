from oppie.models.drift import DriftResult, FieldDrift
from oppie.models.operation import Operation
from oppie.models.plan import Plan, PlanStatus
from tests.helpers import make_ticket, write_ticket


def _make_plan(operations, ticket_snapshots=None):
    return Plan(
        plan_id='testplan1',
        instruction='test instruction',
        operations=operations,
        risks=[],
        created_at='2026-01-01T00:00:00Z',
        status=PlanStatus.SAVED,
        ticket_snapshots=ticket_snapshots,
    )


# --- _check_drift ---


def test_no_drift_when_state_unchanged(plan_engine):
    ticket = make_ticket('T-1', status='open')
    write_ticket(plan_engine._home, ticket)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = _make_plan(ops)

    result = plan_engine._check_drift(plan)

    assert not result.has_any
    assert result.critical_drifts == []
    assert result.informational_drifts == []
    assert result.deleted_tickets == []


def test_critical_drift_field_changed(plan_engine):
    ticket = make_ticket('T-1', status='in_progress')
    write_ticket(plan_engine._home, ticket)
    # Plan recorded before_value as 'open', but ticket is now 'in_progress'
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = _make_plan(ops)

    result = plan_engine._check_drift(plan)

    assert result.has_critical
    assert len(result.critical_drifts) == 1
    assert result.critical_drifts[0].ticket_id == 'T-1'
    assert result.critical_drifts[0].field == 'status'
    assert result.critical_drifts[0].expected_value == 'open'
    assert result.critical_drifts[0].current_value == 'in_progress'


def test_critical_drift_multiple_fields(plan_engine):
    ticket = make_ticket('T-1', status='in_progress', priority='high')
    write_ticket(plan_engine._home, ticket)
    ops = [
        Operation('T-1', 'status', 'open', 'done', 'closing'),
        Operation('T-1', 'priority', 'low', 'high', 'escalating'),
    ]
    plan = _make_plan(ops)

    result = plan_engine._check_drift(plan)

    assert len(result.critical_drifts) == 2
    drifted_fields = {d.field for d in result.critical_drifts}
    assert drifted_fields == {'status', 'priority'}


def test_informational_drift_other_field_changed(plan_engine):
    original_ticket = make_ticket('T-1', status='open', owner='alice')

    # Now change owner (a field NOT in the plan's operations)
    modified_ticket = make_ticket('T-1', status='open', owner='bob')
    write_ticket(plan_engine._home, modified_ticket)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = _make_plan(ops, ticket_snapshots={'T-1': original_ticket})

    result = plan_engine._check_drift(plan)

    assert not result.has_critical
    assert result.has_any
    assert len(result.informational_drifts) == 1
    assert result.informational_drifts[0].field == 'owner'
    assert result.informational_drifts[0].expected_value == 'alice'
    assert result.informational_drifts[0].current_value == 'bob'


def test_informational_drift_skipped_without_snapshots(plan_engine):
    ticket = make_ticket('T-1', status='open', owner='bob')
    write_ticket(plan_engine._home, ticket)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    # No ticket_snapshots
    plan = _make_plan(ops, ticket_snapshots=None)

    result = plan_engine._check_drift(plan)

    assert result.informational_drifts == []


def test_deleted_ticket_detected(plan_engine):
    # Don't write any ticket — it's "deleted"
    ops = [Operation('T-GONE', 'status', 'open', 'done', 'closing')]
    plan = _make_plan(ops)

    result = plan_engine._check_drift(plan)

    assert result.has_critical
    assert result.deleted_tickets == ['T-GONE']


def test_deleted_ticket_plus_drift(plan_engine):
    # T-1 has drift, T-2 is deleted
    ticket = make_ticket('T-1', status='in_progress')
    write_ticket(plan_engine._home, ticket)
    ops = [
        Operation('T-1', 'status', 'open', 'done', 'closing'),
        Operation('T-2', 'status', 'open', 'done', 'closing'),
    ]
    plan = _make_plan(ops)

    result = plan_engine._check_drift(plan)

    assert result.has_critical
    assert len(result.critical_drifts) == 1
    assert result.critical_drifts[0].ticket_id == 'T-1'
    assert result.deleted_tickets == ['T-2']


def test_no_drift_labels_different_order(plan_engine):
    # Ticket has labels in different order than plan's before_value
    ticket = make_ticket('T-1', labels=['b', 'a'])
    write_ticket(plan_engine._home, ticket)
    ops = [Operation('T-1', 'labels', ['a', 'b'], ['a', 'b', 'c'], 'add label')]
    plan = _make_plan(ops)

    result = plan_engine._check_drift(plan)

    assert not result.has_any


def test_field_now_null_is_drift(plan_engine):
    ticket = make_ticket('T-1')
    # Set owner to None
    ticket.owner = None
    write_ticket(plan_engine._home, ticket)
    # Plan recorded before_value as 'alice'
    ops = [Operation('T-1', 'owner', 'alice', 'bob', 'reassign')]
    plan = _make_plan(ops)

    result = plan_engine._check_drift(plan)

    assert result.has_critical
    assert len(result.critical_drifts) == 1
    assert result.critical_drifts[0].expected_value == 'alice'
    assert result.critical_drifts[0].current_value is None


# --- DriftResult properties ---


def test_has_critical_property():
    # Critical drifts
    result = DriftResult(
        critical_drifts=[FieldDrift('T-1', 'status', 'open', 'closed')],
    )

    assert result.has_critical is True

    # Deleted tickets
    result = DriftResult(deleted_tickets=['T-1'])

    assert result.has_critical is True

    # Neither
    result = DriftResult()

    assert result.has_critical is False


def test_has_any_property():
    # Only informational
    result = DriftResult(
        informational_drifts=[FieldDrift('T-1', 'owner', 'alice', 'bob')],
    )

    assert result.has_any is True
    assert result.has_critical is False

    # Empty
    result = DriftResult()

    assert result.has_any is False


# --- Serialization ---


def test_drift_result_serialization():
    result = DriftResult(
        critical_drifts=[FieldDrift('T-1', 'status', 'open', 'closed')],
        informational_drifts=[FieldDrift('T-1', 'owner', 'alice', 'bob')],
        deleted_tickets=['T-2'],
    )

    data = result.to_dict()
    restored = DriftResult.from_dict(data)

    assert len(restored.critical_drifts) == 1
    assert restored.critical_drifts[0].ticket_id == 'T-1'
    assert restored.critical_drifts[0].field == 'status'
    assert len(restored.informational_drifts) == 1
    assert restored.informational_drifts[0].field == 'owner'
    assert restored.deleted_tickets == ['T-2']
