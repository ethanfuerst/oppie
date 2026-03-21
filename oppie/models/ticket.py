import dataclasses
from dataclasses import dataclass
from enum import Enum

SCHEMA_VERSION = 'v1'


class TicketSource(Enum):
    LINEAR = 'linear'
    LOCAL = 'local'


@dataclass
class TicketMetadata:
    source: TicketSource
    external_id: str | None = None
    synced_at: str | None = None

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d['source'] = self.source.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> 'TicketMetadata':
        return cls(
            source=TicketSource(data['source']),
            external_id=data.get('external_id'),
            synced_at=data.get('synced_at'),
        )


@dataclass
class Ticket:
    id: str
    title: str
    status: str
    priority: str
    owner: str | None
    labels: list[str]
    created_at: str
    updated_at: str
    project: str | None
    description: str
    metadata: TicketMetadata

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d['metadata'] = self.metadata.to_dict()
        return {'schema_version': SCHEMA_VERSION, **d}

    @classmethod
    def from_dict(cls, data: dict) -> 'Ticket':
        data = dict(data)  # shallow copy
        schema_version = data.pop('schema_version', None)
        if schema_version != SCHEMA_VERSION:
            raise ValueError(
                f'Unsupported schema version: {schema_version!r} '
                f'(expected {SCHEMA_VERSION!r})'
            )
        data['metadata'] = TicketMetadata.from_dict(data['metadata'])
        return cls(**data)
