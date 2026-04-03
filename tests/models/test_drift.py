from oppie.models.drift import FieldDrift


def test_field_drift_with_updated_at():
    drift = FieldDrift(
        ticket_id='T-1',
        field='status',
        expected_value='open',
        current_value='closed',
        updated_at='2026-03-01T12:00:00Z',
    )

    d = drift.to_dict()

    assert d['updated_at'] == '2026-03-01T12:00:00Z'
    assert d['updated_by'] is None

    roundtripped = FieldDrift.from_dict(d)

    assert roundtripped.updated_at == '2026-03-01T12:00:00Z'
    assert roundtripped.updated_by is None


def test_field_drift_from_dict_without_new_fields():
    """Backwards compatibility: old data without updated_at/updated_by."""
    d = {
        'ticket_id': 'T-1',
        'field': 'status',
        'expected_value': 'open',
        'current_value': 'closed',
    }
    drift = FieldDrift.from_dict(d)

    assert drift.updated_at is None
    assert drift.updated_by is None
