from oppie.models.operation import Operation


def test_operation_construction():
    op = Operation(
        ticket_id='TICKET-001',
        field='status',
        before_value='todo',
        after_value='in_progress',
        rationale='Starting work',
    )

    assert op.ticket_id == 'TICKET-001'
    assert op.field == 'status'
    assert op.before_value == 'todo'
    assert op.after_value == 'in_progress'


def test_operation_with_list_values():
    op = Operation(
        ticket_id='TICKET-001',
        field='labels',
        before_value=['bug'],
        after_value=['bug', 'security'],
        rationale='Add security label',
    )

    assert op.before_value == ['bug']
    assert op.after_value == ['bug', 'security']


def test_operation_with_none_values():
    op = Operation(
        ticket_id='TICKET-001',
        field='owner',
        before_value=None,
        after_value='dev@example.com',
        rationale='Assign to dev',
    )

    assert op.before_value is None


def test_operation_roundtrip():
    op = Operation(
        ticket_id='TICKET-001',
        field='priority',
        before_value='low',
        after_value='high',
        rationale='Escalate',
    )
    result = Operation.from_dict(op.to_dict())

    assert result == op


def test_operation_to_dict():
    op = Operation(
        ticket_id='T-1',
        field='status',
        before_value='todo',
        after_value='done',
        rationale='Complete',
    )
    d = op.to_dict()

    assert d == {
        'ticket_id': 'T-1',
        'field': 'status',
        'before_value': 'todo',
        'after_value': 'done',
        'rationale': 'Complete',
    }
