import pytest

from oppie.models.ticket import SCHEMA_VERSION, Ticket, TicketMetadata, TicketSource


def test_ticket_source_values():
    assert TicketSource.LINEAR.value == 'linear'
    assert TicketSource.LOCAL.value == 'local'


def test_ticket_metadata_construction():
    meta = TicketMetadata(
        source=TicketSource.LINEAR,
        external_id='LIN-123',
        synced_at='2026-02-04T15:30:00Z',
    )

    assert meta.source == TicketSource.LINEAR
    assert meta.external_id == 'LIN-123'
    assert meta.synced_at == '2026-02-04T15:30:00Z'


def test_ticket_metadata_defaults():
    meta = TicketMetadata(source=TicketSource.LOCAL)

    assert meta.external_id is None
    assert meta.synced_at is None


def test_ticket_metadata_to_dict_serializes_source():
    meta = TicketMetadata(source=TicketSource.LINEAR)
    d = meta.to_dict()

    assert d['source'] == 'linear'


def test_ticket_metadata_roundtrip():
    meta = TicketMetadata(
        source=TicketSource.LINEAR,
        external_id='LIN-123',
        synced_at='2026-02-04T15:30:00Z',
    )
    result = TicketMetadata.from_dict(meta.to_dict())

    assert result == meta


def test_ticket_construction():
    ticket = Ticket(
        id='TICKET-001',
        title='Fix login bug',
        status='in_progress',
        priority='high',
        owner='user@example.com',
        labels=['bug', 'security'],
        created_at='2026-02-04T10:00:00Z',
        updated_at='2026-02-04T15:30:00Z',
        project='auth-system',
        description='Users cannot log in with 2FA enabled...',
        metadata=TicketMetadata(
            source=TicketSource.LINEAR,
            external_id='LIN-123',
            synced_at='2026-02-04T15:30:00Z',
        ),
    )

    assert ticket.id == 'TICKET-001'
    assert ticket.labels == ['bug', 'security']
    assert ticket.metadata.source == TicketSource.LINEAR


def test_ticket_to_dict_includes_schema_version():
    ticket = Ticket(
        id='TICKET-001',
        title='Test',
        status='todo',
        priority='medium',
        owner=None,
        labels=[],
        created_at='2026-01-01T00:00:00Z',
        updated_at='2026-01-01T00:00:00Z',
        project=None,
        description='desc',
        metadata=TicketMetadata(source=TicketSource.LOCAL),
    )
    d = ticket.to_dict()

    assert d['schema_version'] == SCHEMA_VERSION
    assert list(d.keys())[0] == 'schema_version'


def test_ticket_to_dict_serializes_source_as_string():
    ticket = Ticket(
        id='T-1',
        title='Test',
        status='todo',
        priority='low',
        owner=None,
        labels=[],
        created_at='2026-01-01T00:00:00Z',
        updated_at='2026-01-01T00:00:00Z',
        project=None,
        description='desc',
        metadata=TicketMetadata(source=TicketSource.LINEAR),
    )
    d = ticket.to_dict()

    assert d['metadata']['source'] == 'linear'


def test_ticket_roundtrip():
    ticket = Ticket(
        id='TICKET-002',
        title='Add feature',
        status='todo',
        priority='low',
        owner='dev@example.com',
        labels=['feature'],
        created_at='2026-03-01T09:00:00Z',
        updated_at='2026-03-01T09:00:00Z',
        project='core',
        description='Add the thing',
        metadata=TicketMetadata(
            source=TicketSource.LINEAR,
            external_id='LIN-456',
            synced_at='2026-03-01T09:00:00Z',
        ),
    )
    result = Ticket.from_dict(ticket.to_dict())

    assert result == ticket


def test_ticket_from_dict_rejects_wrong_schema_version():
    data = {
        'schema_version': 'v99',
        'id': 'T-1',
        'title': 'x',
        'status': 'todo',
        'priority': 'low',
        'owner': None,
        'labels': [],
        'created_at': '2026-01-01T00:00:00Z',
        'updated_at': '2026-01-01T00:00:00Z',
        'project': None,
        'description': '',
        'metadata': {'source': 'local'},
    }

    with pytest.raises(ValueError, match='Unsupported schema version'):
        Ticket.from_dict(data)


def test_ticket_from_dict_rejects_missing_schema_version():
    data = {
        'id': 'T-1',
        'title': 'x',
        'status': 'todo',
        'priority': 'low',
        'owner': None,
        'labels': [],
        'created_at': '2026-01-01T00:00:00Z',
        'updated_at': '2026-01-01T00:00:00Z',
        'project': None,
        'description': '',
        'metadata': {'source': 'local'},
    }

    with pytest.raises(ValueError, match='Unsupported schema version'):
        Ticket.from_dict(data)
