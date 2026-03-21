import dataclasses
from dataclasses import dataclass
from enum import Enum

from oppie.models.operation import Operation


class OperationStatus(Enum):
    OK = 'ok'
    FAILED = 'failed'
    SKIPPED = 'skipped'


@dataclass
class OperationResult:
    operation: Operation
    status: OperationStatus
    error: str | None = None

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d['status'] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> 'OperationResult':
        data = dict(data)
        data['operation'] = Operation.from_dict(data['operation'])
        data['status'] = OperationStatus(data['status'])
        return cls(**data)


@dataclass
class ApplyResult:
    apply_id: str
    plan_id: str
    results: list[OperationResult]
    duration: float
    created_at: str

    def to_dict(self) -> dict:
        return {
            'apply_id': self.apply_id,
            'plan_id': self.plan_id,
            'results': [r.to_dict() for r in self.results],
            'duration': self.duration,
            'created_at': self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'ApplyResult':
        data = dict(data)
        data['results'] = [OperationResult.from_dict(r) for r in data['results']]
        return cls(**data)
