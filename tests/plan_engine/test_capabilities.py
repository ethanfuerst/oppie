from oppie.models.operation import Operation
from tests.helpers import make_ticket, write_ticket


def test_validate_operations_valid(home, provider):
    ticket = make_ticket(ticket_id='T-1', status='open')
    write_ticket(home, ticket)
    op = Operation('T-1', 'status', 'wrong_before', 'done', 'closing')

    errors = provider.validate_operations([op])

    assert errors == []
    assert op.before_value == 'wrong_before'  # NOT overwritten


def test_validate_operations_ticket_not_found(provider):
    op = Operation('MISSING-1', 'status', 'open', 'done', 'closing')

    errors = provider.validate_operations([op])

    assert len(errors) == 1
    assert 'Ticket not found' in errors[0]


def test_validate_operations_unsupported_field(home, provider):
    ticket = make_ticket(ticket_id='T-1')
    write_ticket(home, ticket)
    op = Operation('T-1', 'nonexistent_field', None, 'val', 'test')

    errors = provider.validate_operations([op])

    assert len(errors) == 1
    assert 'does not support updating field' in errors[0]
