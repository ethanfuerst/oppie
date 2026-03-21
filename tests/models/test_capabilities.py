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
    )
    restored = ProviderCapabilities.from_dict(caps.to_dict())

    assert restored == caps
