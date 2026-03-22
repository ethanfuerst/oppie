import json
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path

from oppie.models.capabilities import ProviderCapabilities
from oppie.models.ticket import Ticket
from oppie.providers.base import TicketProvider


@dataclass
class TicketFilter:
    status: str | None = None
    priority: str | None = None
    project: str | None = None
    owner: str | None = None
    labels: list[str] | None = None


class LocalProvider(TicketProvider):
    """File-backed ticket storage with SQLite indexing."""

    _UPDATABLE_FIELDS = [
        'title',
        'status',
        'priority',
        'owner',
        'labels',
        'created_at',
        'updated_at',
        'project',
        'description',
    ]

    def __init__(self, home: Path) -> None:
        self._home = home
        self._tickets_dir = home / 'tickets'
        self._db_path = home / 'state' / 'cache.sqlite'
        self._conn = self._open_db()
        self._ensure_schema()

    @property
    def capabilities(self) -> ProviderCapabilities:
        """Return capabilities for the local provider."""
        return ProviderCapabilities(
            supports_sync=True,
            supports_write=True,
            supports_create=True,
            supported_field_updates=list(self._UPDATABLE_FIELDS),
        )

    def _open_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.execute('PRAGMA journal_mode=WAL')
        return conn

    def _ensure_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS tickets (
                ticket_id TEXT PRIMARY KEY,
                status TEXT,
                priority TEXT,
                project TEXT,
                owner TEXT,
                title TEXT,
                description TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
            CREATE INDEX IF NOT EXISTS idx_tickets_priority ON tickets(priority);
            CREATE INDEX IF NOT EXISTS idx_tickets_project ON tickets(project);
            CREATE INDEX IF NOT EXISTS idx_tickets_owner ON tickets(owner);

            CREATE TABLE IF NOT EXISTS ticket_labels (
                ticket_id TEXT NOT NULL,
                label TEXT NOT NULL,
                PRIMARY KEY (ticket_id, label),
                FOREIGN KEY (ticket_id) REFERENCES tickets(ticket_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_ticket_labels_label ON ticket_labels(label);
        """)

    def _write_ticket_file(self, ticket: Ticket) -> None:
        target = self._tickets_dir / f'{ticket.id}.json'
        fd, tmp_path = tempfile.mkstemp(dir=self._tickets_dir, suffix='.tmp')
        try:
            with open(fd, 'w') as f:
                json.dump(ticket.to_dict(), f, indent=2)
                f.write('\n')
            Path(tmp_path).replace(target)
        except BaseException:
            Path(tmp_path).unlink(missing_ok=True)
            raise

    def _index_ticket(self, ticket: Ticket) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO tickets
               (ticket_id, status, priority, project, owner, title, description)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                ticket.id,
                ticket.status,
                ticket.priority,
                ticket.project,
                ticket.owner,
                ticket.title,
                ticket.description,
            ),
        )
        self._conn.execute(
            'DELETE FROM ticket_labels WHERE ticket_id = ?', (ticket.id,)
        )
        self._conn.executemany(
            'INSERT INTO ticket_labels (ticket_id, label) VALUES (?, ?)',
            [(ticket.id, label) for label in ticket.labels],
        )
        self._conn.commit()

    def _remove_index(self, ticket_id: str) -> None:
        self._conn.execute(
            'DELETE FROM ticket_labels WHERE ticket_id = ?', (ticket_id,)
        )
        self._conn.execute('DELETE FROM tickets WHERE ticket_id = ?', (ticket_id,))
        self._conn.commit()

    def create_ticket(self, ticket: Ticket) -> Ticket:
        path = self._tickets_dir / f'{ticket.id}.json'
        if path.exists():
            raise FileExistsError(f'Ticket already exists: {ticket.id}')
        self._write_ticket_file(ticket)
        self._index_ticket(ticket)
        return ticket

    def read_ticket(self, ticket_id: str) -> Ticket | None:
        path = self._tickets_dir / f'{ticket_id}.json'
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        return Ticket.from_dict(data)

    def update_ticket(self, ticket_id: str, updates: dict) -> Ticket:
        ticket = self.read_ticket(ticket_id)
        if ticket is None:
            raise FileNotFoundError(f'Ticket not found: {ticket_id}')
        for field_name, value in updates.items():
            if field_name in ('id', 'metadata'):
                raise ValueError(f'Cannot update field: {field_name!r}')
            if not hasattr(ticket, field_name):
                raise ValueError(f'Unknown ticket field: {field_name!r}')
            setattr(ticket, field_name, value)
        self._write_ticket_file(ticket)
        self._index_ticket(ticket)
        return ticket

    def delete_ticket(self, ticket_id: str) -> bool:
        path = self._tickets_dir / f'{ticket_id}.json'
        if not path.exists():
            return False
        path.unlink()
        self._remove_index(ticket_id)
        return True

    def list_tickets(self, filters: TicketFilter | None = None) -> list[Ticket]:
        if filters is None:
            tickets = []
            for path in sorted(self._tickets_dir.glob('*.json')):
                data = json.loads(path.read_text())
                tickets.append(Ticket.from_dict(data))
            return tickets

        clauses: list[str] = []
        params: list[str] = []

        for field_name in ('status', 'priority', 'project', 'owner'):
            value = getattr(filters, field_name)
            if value is not None:
                clauses.append(f't.{field_name} = ?')
                params.append(value)

        join = ''
        if filters.labels is not None:
            join = ' JOIN ticket_labels tl ON t.ticket_id = tl.ticket_id'
            placeholders = ', '.join('?' for _ in filters.labels)
            clauses.append(f'tl.label IN ({placeholders})')
            params.extend(filters.labels)

        where = f' WHERE {" AND ".join(clauses)}' if clauses else ''
        query = f'SELECT DISTINCT t.ticket_id FROM tickets t{join}{where}'

        rows = self._conn.execute(query, params).fetchall()
        ticket_ids = [row[0] for row in rows]

        tickets = []
        for ticket_id in ticket_ids:
            ticket = self.read_ticket(ticket_id)
            if ticket is not None:
                tickets.append(ticket)
        return tickets

    def search_tickets(self, query: str) -> list[Ticket]:
        pattern = f'%{query}%'
        rows = self._conn.execute(
            """SELECT ticket_id FROM tickets
               WHERE title LIKE ? OR description LIKE ?""",
            (pattern, pattern),
        ).fetchall()

        tickets = []
        for (ticket_id,) in rows:
            ticket = self.read_ticket(ticket_id)
            if ticket is not None:
                tickets.append(ticket)
        return tickets

    def upsert_ticket(self, ticket: Ticket) -> Ticket:
        self._write_ticket_file(ticket)
        self._index_ticket(ticket)
        return ticket

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> 'LocalProvider':
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
