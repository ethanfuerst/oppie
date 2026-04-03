import dataclasses
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DriftResolution(Enum):
    KEEP_PLAN_VALUE = 'keep_plan_value'
    KEEP_CURRENT_VALUE = 'keep_current_value'
    SKIP_OPERATION = 'skip_operation'


@dataclass(slots=True)
class FieldDrift:
    ticket_id: str
    field: str
    expected_value: Any
    current_value: Any
    updated_at: str | None = None
    updated_by: str | None = None

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'FieldDrift':
        return cls(
            ticket_id=data['ticket_id'],
            field=data['field'],
            expected_value=data['expected_value'],
            current_value=data['current_value'],
            updated_at=data.get('updated_at'),
            updated_by=data.get('updated_by'),
        )


@dataclass(slots=True)
class DriftResult:
    critical_drifts: list[FieldDrift] = field(default_factory=list)
    informational_drifts: list[FieldDrift] = field(default_factory=list)
    deleted_tickets: list[str] = field(default_factory=list)

    @property
    def has_critical(self) -> bool:
        return bool(self.critical_drifts) or bool(self.deleted_tickets)

    @property
    def has_any(self) -> bool:
        return self.has_critical or bool(self.informational_drifts)

    def to_dict(self) -> dict:
        return {
            'critical_drifts': [d.to_dict() for d in self.critical_drifts],
            'informational_drifts': [d.to_dict() for d in self.informational_drifts],
            'deleted_tickets': list(self.deleted_tickets),
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'DriftResult':
        return cls(
            critical_drifts=[
                FieldDrift.from_dict(d) for d in data.get('critical_drifts', [])
            ],
            informational_drifts=[
                FieldDrift.from_dict(d) for d in data.get('informational_drifts', [])
            ],
            deleted_tickets=data.get('deleted_tickets', []),
        )
