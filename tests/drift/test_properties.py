from oppie.models.drift import DriftResult, FieldDrift


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
