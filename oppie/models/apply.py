import dataclasses
import json
from dataclasses import dataclass
from enum import Enum

from oppie.models.operation import Operation
from oppie.models.plan import Plan


class OperationStatus(Enum):
    OK = 'ok'
    FAILED = 'failed'
    SKIPPED = 'skipped'


@dataclass(slots=True)
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


@dataclass(slots=True)
class ApplyResult:
    apply_id: str
    plan: Plan
    results: list[OperationResult]
    duration: float
    created_at: str

    @property
    def plan_id(self) -> str:
        return self.plan.plan_id

    def to_dict(self) -> dict:
        return {
            'apply_id': self.apply_id,
            'plan': self.plan.to_dict(),
            'results': [r.to_dict() for r in self.results],
            'duration': self.duration,
            'created_at': self.created_at,
        }

    def build_artifact(self) -> str:
        """Build JSON content for the apply artifact."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> 'ApplyResult':
        data = dict(data)
        data['plan'] = Plan.from_dict(data['plan'])
        data['results'] = [OperationResult.from_dict(r) for r in data['results']]
        return cls(**data)
