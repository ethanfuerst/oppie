import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from oppie.models import RunId


def generate_run_id() -> RunId:
    """Generate a unique run ID."""
    return str(uuid.uuid4())


@dataclass(slots=True)
class RunLogEntry:
    run_id: RunId
    command: str
    timestamp: str
    duration: float
    artifact_paths: list[str] = field(default_factory=list)
    plan_id: str | None = None
    apply_id: str | None = None
    token_usage: dict[str, int] | None = None

    def to_dict(self) -> dict:
        return {
            'run_id': self.run_id,
            'command': self.command,
            'timestamp': self.timestamp,
            'duration': self.duration,
            'artifact_paths': self.artifact_paths,
            'plan_id': self.plan_id,
            'apply_id': self.apply_id,
            'token_usage': self.token_usage,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'RunLogEntry':
        return cls(
            run_id=data['run_id'],
            command=data['command'],
            timestamp=data['timestamp'],
            duration=data['duration'],
            artifact_paths=data.get('artifact_paths', []),
            plan_id=data.get('plan_id'),
            apply_id=data.get('apply_id'),
            token_usage=data.get('token_usage'),
        )


class RunLog:
    """Manage append-only run log at logs/runs.jsonl."""

    def __init__(self, home: Path) -> None:
        self._log_path = home / 'logs' / 'runs.jsonl'

    def append(self, entry: RunLogEntry) -> None:
        """Append a run log entry. Never overwrites existing entries."""
        line = json.dumps(entry.to_dict(), separators=(',', ':')) + '\n'
        with open(self._log_path, 'a') as f:
            f.write(line)

    def query(
        self,
        limit: int | None = None,
        command_type: str | None = None,
    ) -> list[RunLogEntry]:
        """Read and filter run log entries.

        Returns entries in chronological order (oldest first).
        Filters by command_type if provided. Limits to last N entries if limit provided.
        """
        if not self._log_path.exists():
            return []

        entries: list[RunLogEntry] = []
        for line in self._log_path.read_text().splitlines():
            if not line.strip():
                continue
            entry = RunLogEntry.from_dict(json.loads(line))
            if command_type is not None and entry.command != command_type:
                continue
            entries.append(entry)

        if limit is not None:
            entries = entries[-limit:]

        return entries
