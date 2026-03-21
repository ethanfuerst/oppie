from oppie.models.apply import ApplyResult, OperationResult, OperationStatus
from oppie.models.operation import Operation
from oppie.models.plan import Plan, PlanStatus


def _make_plan(plan_id='deadbeef'):
    return Plan(
        plan_id=plan_id,
        instruction='test instruction',
        operations=[],
        risks=[],
        created_at='2026-01-01T00:00:00Z',
        status=PlanStatus.SAVED,
    )


def test_operation_status_values():
    assert OperationStatus.OK.value == 'ok'
    assert OperationStatus.FAILED.value == 'failed'
    assert OperationStatus.SKIPPED.value == 'skipped'


def test_operation_result_success():
    op = Operation(
        ticket_id='T-1',
        field='status',
        before_value='todo',
        after_value='done',
        rationale='Done',
    )
    result = OperationResult(operation=op, status=OperationStatus.OK)

    assert result.status == OperationStatus.OK
    assert result.error is None


def test_operation_result_failure():
    op = Operation(
        ticket_id='T-1',
        field='status',
        before_value='todo',
        after_value='done',
        rationale='Done',
    )
    result = OperationResult(
        operation=op, status=OperationStatus.FAILED, error='Ticket not found'
    )

    assert result.error == 'Ticket not found'


def test_operation_result_roundtrip():
    op = Operation(
        ticket_id='T-1',
        field='status',
        before_value='todo',
        after_value='done',
        rationale='Done',
    )
    result = OperationResult(
        operation=op, status=OperationStatus.SKIPPED, error='Drift detected'
    )
    restored = OperationResult.from_dict(result.to_dict())

    assert restored == result


def test_apply_result_construction():
    op = Operation(
        ticket_id='T-1',
        field='status',
        before_value='todo',
        after_value='done',
        rationale='Done',
    )
    results = [
        OperationResult(operation=op, status=OperationStatus.OK),
    ]
    apply_result = ApplyResult(
        apply_id='a1b2c3d4',
        plan=_make_plan(),
        results=results,
        duration=1.5,
        created_at='2026-03-01T11:00:00Z',
    )

    assert apply_result.apply_id == 'a1b2c3d4'
    assert apply_result.plan_id == 'deadbeef'
    assert apply_result.duration == 1.5
    assert len(apply_result.results) == 1


def test_apply_result_mixed_statuses():
    ops = [
        Operation(
            ticket_id='T-1',
            field='status',
            before_value='todo',
            after_value='done',
            rationale='Done',
        ),
        Operation(
            ticket_id='T-2',
            field='priority',
            before_value='low',
            after_value='high',
            rationale='Escalate',
        ),
        Operation(
            ticket_id='T-3',
            field='owner',
            before_value=None,
            after_value='dev@co.com',
            rationale='Assign',
        ),
    ]
    results = [
        OperationResult(operation=ops[0], status=OperationStatus.OK),
        OperationResult(
            operation=ops[1], status=OperationStatus.FAILED, error='Ticket deleted'
        ),
        OperationResult(operation=ops[2], status=OperationStatus.SKIPPED),
    ]
    apply_result = ApplyResult(
        apply_id='id-001',
        plan=_make_plan('plan-001'),
        results=results,
        duration=3.2,
        created_at='2026-03-01T12:00:00Z',
    )

    assert apply_result.results[0].status == OperationStatus.OK
    assert apply_result.results[1].status == OperationStatus.FAILED
    assert apply_result.results[2].status == OperationStatus.SKIPPED


def test_apply_result_roundtrip():
    op = Operation(
        ticket_id='T-1',
        field='status',
        before_value='todo',
        after_value='done',
        rationale='Done',
    )
    apply_result = ApplyResult(
        apply_id='a1b2c3d4',
        plan=_make_plan(),
        results=[OperationResult(operation=op, status=OperationStatus.OK)],
        duration=0.8,
        created_at='2026-03-01T11:00:00Z',
    )
    restored = ApplyResult.from_dict(apply_result.to_dict())

    assert restored == apply_result


def test_apply_result_to_dict_serializes_enums():
    op = Operation(
        ticket_id='T-1',
        field='status',
        before_value='todo',
        after_value='done',
        rationale='Done',
    )
    apply_result = ApplyResult(
        apply_id='id-001',
        plan=_make_plan('plan-001'),
        results=[
            OperationResult(operation=op, status=OperationStatus.FAILED, error='oops')
        ],
        duration=0.1,
        created_at='2026-03-01T11:00:00Z',
    )
    d = apply_result.to_dict()

    assert d['results'][0]['status'] == 'failed'
