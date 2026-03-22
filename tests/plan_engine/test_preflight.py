from oppie.models.operation import Operation
from oppie.plan import PlanEngine
from tests.helpers import make_ticket, write_ticket


def test_preflight_valid_operations(home, provider):
    ticket = make_ticket(ticket_id='T-1', status='open')
    write_ticket(home, ticket)
    engine = PlanEngine(home, provider)
    op = Operation('T-1', 'status', 'wrong_before', 'done', 'closing')

    errors = engine._run_preflight([op])

    assert errors == []
    assert op.before_value == 'open'  # overwritten with actual value


def test_preflight_ticket_not_found(home, provider):
    engine = PlanEngine(home, provider)
    op = Operation('MISSING-1', 'status', 'open', 'done', 'closing')

    errors = engine._run_preflight([op])

    assert len(errors) == 1
    assert 'Ticket not found' in errors[0]


def test_preflight_unsupported_field(home, provider):
    ticket = make_ticket(ticket_id='T-1')
    write_ticket(home, ticket)
    engine = PlanEngine(home, provider)
    op = Operation('T-1', 'nonexistent_field', None, 'val', 'test')

    errors = engine._run_preflight([op])

    assert len(errors) == 1
    assert 'does not support updating field' in errors[0]


def test_preflight_protected_field(home, provider):
    ticket = make_ticket(ticket_id='T-1')
    write_ticket(home, ticket)
    engine = PlanEngine(home, provider)
    op = Operation('T-1', 'id', 'T-1', 'T-999', 'rename')

    errors = engine._run_preflight([op])

    assert len(errors) == 1


def test_preflight_multiple_errors(home, provider):
    engine = PlanEngine(home, provider)
    ops = [
        Operation('MISSING', 'status', 'open', 'done', 'close'),
        Operation('ALSO-MISSING', 'status', 'open', 'done', 'close'),
    ]

    errors = engine._run_preflight(ops)

    assert len(errors) == 2
