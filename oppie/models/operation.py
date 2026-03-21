import dataclasses
from dataclasses import dataclass
from typing import Any


@dataclass
class Operation:
    ticket_id: str
    field: str
    # Any because values can vary by field: str for priority, list[str] for labels, etc.
    before_value: Any
    after_value: Any
    rationale: str

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'Operation':
        return cls(**data)
