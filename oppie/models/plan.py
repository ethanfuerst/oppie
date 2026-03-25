from __future__ import annotations

import dataclasses
import hashlib
import json
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from oppie.models.operation import Operation
from oppie.models.ticket import Ticket

PLAN_INDEX_FILENAME = '.plan-index.jsonl'


class PlanStatus(Enum):
    SAVED = 'saved'
    APPLIED = 'applied'
    INVALID = 'invalid'


@dataclass
class Plan:
    instruction: str
    operations: list[Operation]
    risks: list[str]
    created_at: str
    status: PlanStatus
    parent_plan_id: str | None = None
    ticket_snapshots: dict[str, Ticket] | None = None
    checked: bool = False
    plan_id: str = field(init=False)

    def __post_init__(self) -> None:
        self.plan_id = self.compute_id(self.operations)

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d['status'] = self.status.value
        if self.ticket_snapshots is not None:
            d['ticket_snapshots'] = {
                tid: t.to_dict() for tid, t in self.ticket_snapshots.items()
            }
        return d

    @classmethod
    def from_dict(cls, data: dict) -> Plan:
        data = dict(data)
        stored_plan_id = data.pop('plan_id', None)
        data['operations'] = [Operation.from_dict(op) for op in data['operations']]
        data['status'] = PlanStatus(data['status'])
        if data.get('ticket_snapshots') is not None:
            data['ticket_snapshots'] = {
                tid: Ticket.from_dict(t) for tid, t in data['ticket_snapshots'].items()
            }
        plan = cls(**data)
        # Preserve the on-disk plan_id instead of the freshly computed one.
        # A tampered file will have a plan_id that doesn't match compute_id(),
        # which check_apply() detects as an integrity failure.
        if stored_plan_id is not None:
            plan.plan_id = stored_plan_id
        return plan

    def save(self, home: Path) -> Path:
        """Save plan as JSON and append to plan index.

        Use atomic write (temp file + rename).
        Return the path to the saved JSON file.
        """
        plans_dir = home / 'artifacts' / 'plans'
        plans_dir.mkdir(parents=True, exist_ok=True)
        target = plans_dir / f'plan-{self.plan_id}.json'

        fd, tmp_path = tempfile.mkstemp(dir=plans_dir, suffix='.tmp')
        try:
            with open(fd, 'w') as f:
                json.dump(self.to_dict(), f, indent=2)
                f.write('\n')
            Path(tmp_path).replace(target)
        except BaseException:
            Path(tmp_path).unlink(missing_ok=True)
            raise

        self._append_to_index(plans_dir)
        return target

    def _append_to_index(self, plans_dir: Path) -> None:
        """Append this plan's metadata to the JSONL index."""
        entry = {
            'plan_id': self.plan_id,
            'instruction': self.instruction,
            'created_at': self.created_at,
        }
        index_path = plans_dir / PLAN_INDEX_FILENAME
        with open(index_path, 'a') as f:
            f.write(json.dumps(entry, separators=(',', ':')) + '\n')

    @staticmethod
    def compute_id(operations: list[Operation]) -> str:
        """Compute plan ID from content hash of operations.

        Serialize operations to canonical JSON (sorted keys, compact),
        SHA-256 hash, truncate to 8 hex chars.
        """
        ops_data = [op.to_dict() for op in operations]
        canonical = json.dumps(ops_data, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:8]
