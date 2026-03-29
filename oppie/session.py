import json
import logging
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from oppie.models import PlanId, RunId, SessionId

logger = logging.getLogger(__name__)

MAX_RECENT_RUNS = 10


def generate_session_id() -> SessionId:
    """Generate a unique session ID."""
    return str(uuid.uuid4())


@dataclass
class SessionData:
    session_id: SessionId = ''
    active_plan_id: PlanId | None = None
    recent_run_ids: list[RunId] = field(default_factory=list)
    last_command_at: str | None = None

    def to_dict(self) -> dict:
        return {
            'session_id': self.session_id,
            'active_plan_id': self.active_plan_id,
            'recent_run_ids': self.recent_run_ids,
            'last_command_at': self.last_command_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'SessionData':
        return cls(
            session_id=data.get('session_id', ''),
            active_plan_id=data.get('active_plan_id'),
            recent_run_ids=data.get('recent_run_ids', []),
            last_command_at=data.get('last_command_at'),
        )


class Session:
    """Manage session state at state/session-{id}.json."""

    def __init__(self, home: Path, session_id: SessionId) -> None:
        self._home = home
        self._session_id = session_id
        self._session_path = home / 'state' / f'session-{session_id}.json'

    @property
    def session_id(self) -> SessionId:
        """Return this session's ID."""
        return self._session_id

    @classmethod
    def create(cls, home: Path) -> 'Session':
        """Create a new session with a generated UUID.

        Write the initial session file and return the Session instance.
        """
        session_id = generate_session_id()
        session = cls(home, session_id)
        data = SessionData(
            session_id=session_id,
            last_command_at=datetime.now(UTC).isoformat(),
        )
        session._save(data)
        logger.debug('Created session %s', session_id)
        return session

    @classmethod
    def load(cls, home: Path, session_id: SessionId) -> 'Session':
        """Load an existing session by ID.

        Raise FileNotFoundError if the session file does not exist.
        """
        session = cls(home, session_id)
        if not session._session_path.exists():
            raise FileNotFoundError(f'Session not found: {session_id}')
        logger.debug('Loaded session %s', session_id)
        return session

    @classmethod
    def load_latest(cls, home: Path) -> 'Session | None':
        """Find and load the most recently touched session.

        Return None if no session files exist.
        """
        state_dir = home / 'state'
        if not state_dir.exists():
            return None

        session_files = sorted(
            state_dir.glob('session-*.json'),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not session_files:
            return None

        # Extract session ID from filename: session-{uuid}.json
        filename = session_files[0].stem  # session-{uuid}
        session_id = filename[len('session-') :]
        logger.debug(
            'Found %d session files, latest=%s',
            len(session_files),
            session_id,
        )
        return cls(home, session_id)

    def _load(self) -> SessionData:
        """Load session data from disk. Return empty defaults if missing."""
        if not self._session_path.exists():
            return SessionData(session_id=self._session_id)
        try:
            data = json.loads(self._session_path.read_text())
            return SessionData.from_dict(data)
        except (json.JSONDecodeError, KeyError, ValueError):
            logger.warning(
                'Corrupt session file %s, using defaults', self._session_path
            )
            return SessionData(session_id=self._session_id)

    def _save(self, data: SessionData) -> None:
        """Atomically write session data to disk."""
        self._session_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=self._session_path.parent, suffix='.tmp')
        try:
            with open(fd, 'w') as f:
                json.dump(data.to_dict(), f, indent=2)
                f.write('\n')
            Path(tmp_path).replace(self._session_path)
        except BaseException:
            Path(tmp_path).unlink(missing_ok=True)
            raise

    def get_active_plan(self) -> PlanId | None:
        """Return the active plan ID, or None if unset/cleared."""
        return self._load().active_plan_id

    def set_active_plan(self, plan_id: PlanId) -> None:
        """Set the active plan ID and touch the session."""
        data = self._load()
        data.active_plan_id = plan_id
        data.last_command_at = datetime.now(UTC).isoformat()
        self._save(data)
        logger.debug('Session %s: active_plan=%s', self._session_id, plan_id)

    def get_recent_run_ids(self) -> list[RunId]:
        """Return the list of recent run IDs."""
        return self._load().recent_run_ids

    def add_run_id(self, run_id: RunId) -> None:
        """Append a run ID to the recent list (bounded to MAX_RECENT_RUNS) and touch."""
        data = self._load()
        data.recent_run_ids.append(run_id)
        data.recent_run_ids = data.recent_run_ids[-MAX_RECENT_RUNS:]
        data.last_command_at = datetime.now(UTC).isoformat()
        self._save(data)
        logger.debug('Session %s: added run %s', self._session_id, run_id)

    def get_last_command_at(self) -> str | None:
        """Return the last_command_at timestamp, or None if never touched."""
        return self._load().last_command_at

    def touch(self) -> None:
        """Update last_command_at to now."""
        data = self._load()
        data.last_command_at = datetime.now(UTC).isoformat()
        self._save(data)

    def clear(self) -> None:
        """Reset session to empty defaults (preserving session_id)."""
        self._save(SessionData(session_id=self._session_id))
