from oppie.models.operation import Operation
from oppie.models.plan import Plan, PlanStatus


def test_compute_plan_id_deterministic():
    ops = [
        Operation(
            ticket_id='T-1',
            field='status',
            before_value='todo',
            after_value='done',
            rationale='Done',
        ),
    ]

    assert Plan.compute_id(ops) == Plan.compute_id(ops)


def test_compute_plan_id_is_8_hex_chars():
    ops = [
        Operation(
            ticket_id='T-1',
            field='status',
            before_value='todo',
            after_value='done',
            rationale='Done',
        ),
    ]
    plan_id = Plan.compute_id(ops)

    assert len(plan_id) == 8
    assert all(c in '0123456789abcdef' for c in plan_id)


def test_compute_plan_id_changes_with_different_operations():
    ops_a = [
        Operation(
            ticket_id='T-1',
            field='status',
            before_value='todo',
            after_value='done',
            rationale='Done',
        ),
    ]
    ops_b = [
        Operation(
            ticket_id='T-1',
            field='status',
            before_value='todo',
            after_value='in_progress',
            rationale='Start',
        ),
    ]

    assert Plan.compute_id(ops_a) != Plan.compute_id(ops_b)


def test_compute_plan_id_empty_operations():
    plan_id = Plan.compute_id([])

    assert len(plan_id) == 8


def test_plan_auto_computes_plan_id():
    ops = [
        Operation(
            ticket_id='T-1',
            field='status',
            before_value='todo',
            after_value='done',
            rationale='Done',
        ),
    ]
    plan = Plan(
        instruction='Mark T-1 as done',
        operations=ops,
        risks=['Ticket may have been updated'],
        created_at='2026-03-01T10:00:00Z',
        status=PlanStatus.SAVED,
    )

    assert plan.plan_id == Plan.compute_id(ops)
    assert plan.status == PlanStatus.SAVED
    assert plan.parent_plan_id is None


def test_plan_with_parent():
    ops = [
        Operation(
            ticket_id='T-1',
            field='priority',
            before_value='low',
            after_value='high',
            rationale='Escalate',
        ),
    ]
    plan = Plan(
        instruction='Escalate T-1',
        operations=ops,
        risks=[],
        created_at='2026-03-01T12:00:00Z',
        status=PlanStatus.SAVED,
        parent_plan_id='aabbccdd',
    )

    assert plan.parent_plan_id == 'aabbccdd'


def test_plan_status_values():
    assert PlanStatus.SAVED.value == 'saved'
    assert PlanStatus.APPLIED.value == 'applied'
    assert PlanStatus.INVALID.value == 'invalid'


def test_plan_roundtrip():
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
            rationale='Urgent',
        ),
    ]
    plan = Plan(
        instruction='Update tickets',
        operations=ops,
        risks=['Possible drift'],
        created_at='2026-03-01T10:00:00Z',
        status=PlanStatus.SAVED,
        parent_plan_id='11223344',
    )
    result = Plan.from_dict(plan.to_dict())

    assert result == plan


def test_plan_to_dict_serializes_status_as_string():
    ops = [
        Operation(
            ticket_id='T-1',
            field='status',
            before_value='todo',
            after_value='done',
            rationale='Done',
        ),
    ]
    plan = Plan(
        instruction='test',
        operations=ops,
        risks=[],
        created_at='2026-03-01T10:00:00Z',
        status=PlanStatus.APPLIED,
    )
    d = plan.to_dict()

    assert d['status'] == 'applied'
