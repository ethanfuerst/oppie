from oppie.models.operation import Operation
from oppie.plan.engine import _check_drift
from tests.drift.conftest import make_plan
from tests.helpers import make_ticket, write_ticket


def test_no_drift_when_state_unchanged(home, provider):
    ticket = make_ticket('T-1', status='open')
    write_ticket(home, ticket)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = make_plan(ops)

    result = _check_drift(provider, plan)

    assert not result.has_any
    assert result.critical_drifts == []
    assert result.informational_drifts == []
    assert result.deleted_tickets == []


def test_critical_drift_field_changed(home, provider):
    ticket = make_ticket('T-1', status='in_progress')
    write_ticket(home, ticket)
    # Plan recorded before_value as 'open', but ticket is now 'in_progress'
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = make_plan(ops)

    result = _check_drift(provider, plan)

    assert result.has_critical
    assert len(result.critical_drifts) == 1
    assert result.critical_drifts[0].ticket_id == 'T-1'
    assert result.critical_drifts[0].field == 'status'
    assert result.critical_drifts[0].expected_value == 'open'
    assert result.critical_drifts[0].current_value == 'in_progress'


def test_critical_drift_multiple_fields(home, provider):
    ticket = make_ticket('T-1', status='in_progress', priority='high')
    write_ticket(home, ticket)
    ops = [
        Operation('T-1', 'status', 'open', 'done', 'closing'),
        Operation('T-1', 'priority', 'low', 'high', 'escalating'),
    ]
    plan = make_plan(ops)

    result = _check_drift(provider, plan)

    assert len(result.critical_drifts) == 2
    drifted_fields = {d.field for d in result.critical_drifts}
    assert drifted_fields == {'status', 'priority'}


def test_informational_drift_other_field_changed(home, provider):
    original_ticket = make_ticket('T-1', status='open', owner='alice')

    # Now change owner (a field NOT in the plan's operations)
    modified_ticket = make_ticket('T-1', status='open', owner='bob')
    write_ticket(home, modified_ticket)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = make_plan(ops, ticket_snapshots={'T-1': original_ticket})

    result = _check_drift(provider, plan)

    assert not result.has_critical
    assert result.has_any
    assert len(result.informational_drifts) == 1
    assert result.informational_drifts[0].field == 'owner'
    assert result.informational_drifts[0].expected_value == 'alice'
    assert result.informational_drifts[0].current_value == 'bob'


def test_informational_drift_skipped_without_snapshots(home, provider):
    ticket = make_ticket('T-1', status='open', owner='bob')
    write_ticket(home, ticket)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    # No ticket_snapshots
    plan = make_plan(ops, ticket_snapshots=None)

    result = _check_drift(provider, plan)

    assert result.informational_drifts == []


def test_deleted_ticket_detected(home, provider):
    # Don't write any ticket — it's "deleted"
    ops = [Operation('T-GONE', 'status', 'open', 'done', 'closing')]
    plan = make_plan(ops)

    result = _check_drift(provider, plan)

    assert result.has_critical
    assert result.deleted_tickets == ['T-GONE']


def test_deleted_ticket_plus_drift(home, provider):
    # T-1 has drift, T-2 is deleted
    ticket = make_ticket('T-1', status='in_progress')
    write_ticket(home, ticket)
    ops = [
        Operation('T-1', 'status', 'open', 'done', 'closing'),
        Operation('T-2', 'status', 'open', 'done', 'closing'),
    ]
    plan = make_plan(ops)

    result = _check_drift(provider, plan)

    assert result.has_critical
    assert len(result.critical_drifts) == 1
    assert result.critical_drifts[0].ticket_id == 'T-1'
    assert result.deleted_tickets == ['T-2']


def test_no_drift_labels_different_order(home, provider):
    # Ticket has labels in different order than plan's before_value
    ticket = make_ticket('T-1', labels=['b', 'a'])
    write_ticket(home, ticket)
    ops = [Operation('T-1', 'labels', ['a', 'b'], ['a', 'b', 'c'], 'add label')]
    plan = make_plan(ops)

    result = _check_drift(provider, plan)

    assert not result.has_any


def test_field_now_null_is_drift(home, provider):
    ticket = make_ticket('T-1')
    # Set owner to None
    ticket.owner = None
    write_ticket(home, ticket)
    # Plan recorded before_value as 'alice'
    ops = [Operation('T-1', 'owner', 'alice', 'bob', 'reassign')]
    plan = make_plan(ops)

    result = _check_drift(provider, plan)

    assert result.has_critical
    assert len(result.critical_drifts) == 1
    assert result.critical_drifts[0].expected_value == 'alice'
    assert result.critical_drifts[0].current_value is None
