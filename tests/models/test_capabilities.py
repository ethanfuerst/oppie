from oppie.models.capabilities import ProviderCapabilities
from oppie.models.operation import Operation


def test_capabilities_defaults():
    caps = ProviderCapabilities()

    assert caps.supports_sync is True
    assert caps.supports_write is False
    assert caps.supported_field_updates == []


def test_validate_operation_write_not_supported():
    caps = ProviderCapabilities(supports_write=False)
    op = Operation(
        ticket_id='T-1',
        field='status',
        before_value='todo',
        after_value='done',
        rationale='Done',
    )
    error = caps.validate_operation(op)

    assert error is not None
    assert 'write' in error.lower()


def test_validate_operation_field_not_supported():
    caps = ProviderCapabilities(
        supports_write=True,
        supported_field_updates=['status', 'priority'],
    )
    op = Operation(
        ticket_id='T-1',
        field='owner',
        before_value=None,
        after_value='dev@co.com',
        rationale='Assign',
    )
    error = caps.validate_operation(op)

    assert error is not None
    assert 'owner' in error


def test_validate_operation_success():
    caps = ProviderCapabilities(
        supports_write=True,
        supported_field_updates=['status', 'priority', 'labels'],
    )
    op = Operation(
        ticket_id='T-1',
        field='status',
        before_value='todo',
        after_value='done',
        rationale='Done',
    )
    error = caps.validate_operation(op)

    assert error is None


def test_validate_operation_all_supported_fields():
    fields = ['status', 'priority', 'assignee', 'labels', 'estimate']
    caps = ProviderCapabilities(supports_write=True, supported_field_updates=fields)
    for f in fields:
        op = Operation(
            ticket_id='T-1',
            field=f,
            before_value='a',
            after_value='b',
            rationale='test',
        )
        error = caps.validate_operation(op)

        assert error is None


def test_capabilities_roundtrip():
    caps = ProviderCapabilities(
        supports_sync=True,
        supports_incremental_sync=True,
        supports_write=True,
        supports_create=False,
        supports_projects=True,
        supports_estimates=True,
        supports_cycles=True,
        supports_custom_fields=False,
        supported_field_updates=['status', 'priority', 'assignee'],
        field_constraints={'status': ['open', 'done'], 'owner': None},
    )
    restored = ProviderCapabilities.from_dict(caps.to_dict())

    assert restored == caps


def test_validate_operation_value_allowed():
    caps = ProviderCapabilities(
        supports_write=True,
        supported_field_updates=['status'],
        field_constraints={'status': ['open', 'done']},
    )
    op = Operation(
        ticket_id='T-1',
        field='status',
        before_value='open',
        after_value='done',
        rationale='close it',
    )

    assert caps.validate_operation_value(op) is None


def test_validate_operation_value_rejected():
    caps = ProviderCapabilities(
        supports_write=True,
        supported_field_updates=['status'],
        field_constraints={'status': ['open', 'done']},
    )
    op = Operation(
        ticket_id='T-1',
        field='status',
        before_value='open',
        after_value='banana',
        rationale='oops',
    )

    result = caps.validate_operation_value(op)

    assert 'banana' in result
    assert 'Allowed' in result


def test_validate_operation_value_freeform():
    caps = ProviderCapabilities(
        supports_write=True,
        supported_field_updates=['owner'],
        field_constraints={'owner': None},
    )
    op = Operation(
        ticket_id='T-1',
        field='owner',
        before_value=None,
        after_value='alice',
        rationale='assign',
    )

    assert caps.validate_operation_value(op) is None


def test_validate_operation_value_no_constraints():
    caps = ProviderCapabilities(
        supports_write=True,
        supported_field_updates=['title'],
    )
    op = Operation(
        ticket_id='T-1',
        field='title',
        before_value='old',
        after_value='new',
        rationale='rename',
    )

    assert caps.validate_operation_value(op) is None


def test_format_constraints_for_prompt():
    caps = ProviderCapabilities(
        supports_write=True,
        supported_field_updates=['status', 'owner'],
        field_constraints={'status': ['open', 'done'], 'owner': None},
    )

    result = caps.format_constraints_for_prompt()

    assert 'status: open, done' in result
    assert 'owner: (free-form text)' in result
