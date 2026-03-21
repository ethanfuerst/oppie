from dataclasses import dataclass, field


@dataclass
class SyncResult:
    tickets_upserted: int
    checkpoint: str | None = None
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'tickets_upserted': self.tickets_upserted,
            'checkpoint': self.checkpoint,
            'errors': list(self.errors),
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'SyncResult':
        return cls(**data)
