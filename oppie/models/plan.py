from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from oppie.models.operation import Operation
from oppie.models.ticket import Ticket

if TYPE_CHECKING:
    from pathlib import Path

    from oppie.config import OppieConfig
    from oppie.models.plan_engine import PlanEngine
    from oppie.providers.base import TicketProvider


class PlanStatus(Enum):
    SAVED = 'saved'
    APPLIED = 'applied'
    INVALID = 'invalid'


@dataclass
class Plan:
    plan_id: str
    instruction: str
    operations: list[Operation]
    risks: list[str]
    created_at: str
    status: PlanStatus
    parent_plan_id: str | None = None
    ticket_snapshots: dict[str, Ticket] | None = None

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
        data['operations'] = [Operation.from_dict(op) for op in data['operations']]
        data['status'] = PlanStatus(data['status'])
        if data.get('ticket_snapshots') is not None:
            data['ticket_snapshots'] = {
                tid: Ticket.from_dict(t) for tid, t in data['ticket_snapshots'].items()
            }
        return cls(**data)

    @classmethod
    def engine(
        cls,
        home: Path,
        provider: TicketProvider,
        config: OppieConfig | None = None,
    ) -> PlanEngine:
        """Create a PlanEngine for executing plan lifecycle operations."""
        from oppie.models.plan_engine import PlanEngine

        return PlanEngine(home, provider, config)

    @staticmethod
    def compute_id(operations: list[Operation]) -> str:
        """Compute plan ID from content hash of operations.

        Serialize operations to canonical JSON (sorted keys, compact),
        SHA-256 hash, truncate to 8 hex chars.
        """
        ops_data = [op.to_dict() for op in operations]
        canonical = json.dumps(ops_data, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:8]
