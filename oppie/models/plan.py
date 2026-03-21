import dataclasses
import hashlib
import json
from dataclasses import dataclass
from enum import Enum

from oppie.models.operation import Operation


class PlanStatus(Enum):
    SAVED = 'saved'
    APPLIED = 'applied'
    INVALID = 'invalid'


def compute_plan_id(operations: list[Operation]) -> str:
    """Compute plan ID from content hash of operations.

    Serialize operations to canonical JSON (sorted keys, compact),
    SHA-256 hash, truncate to 8 hex chars.
    """
    ops_data = [op.to_dict() for op in operations]
    canonical = json.dumps(ops_data, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:8]


@dataclass
class Plan:
    plan_id: str
    instruction: str
    operations: list[Operation]
    risks: list[str]
    created_at: str
    status: PlanStatus
    parent_plan_id: str | None = None

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d['status'] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> 'Plan':
        data = dict(data)
        data['operations'] = [Operation.from_dict(op) for op in data['operations']]
        data['status'] = PlanStatus(data['status'])
        return cls(**data)
