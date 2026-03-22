from oppie.models.drift import DriftResult, FieldDrift


def test_drift_result_serialization():
    result = DriftResult(
        critical_drifts=[FieldDrift('T-1', 'status', 'open', 'closed')],
        informational_drifts=[FieldDrift('T-1', 'owner', 'alice', 'bob')],
        deleted_tickets=['T-2'],
    )

    data = result.to_dict()
    restored = DriftResult.from_dict(data)

    assert len(restored.critical_drifts) == 1
    assert restored.critical_drifts[0].ticket_id == 'T-1'
    assert restored.critical_drifts[0].field == 'status'
    assert len(restored.informational_drifts) == 1
    assert restored.informational_drifts[0].field == 'owner'
    assert restored.deleted_tickets == ['T-2']
