from oppie.models.sync import SyncResult


def test_sync_result_construction():
    result = SyncResult(tickets_upserted=5, checkpoint='abc123')

    assert result.tickets_upserted == 5
    assert result.checkpoint == 'abc123'
    assert result.errors == []


def test_sync_result_defaults():
    result = SyncResult(tickets_upserted=0)

    assert result.checkpoint is None
    assert result.errors == []


def test_sync_result_roundtrip():
    result = SyncResult(
        tickets_upserted=3,
        checkpoint='cp-1',
        errors=['failed to fetch TICKET-99'],
    )

    assert SyncResult.from_dict(result.to_dict()) == result
