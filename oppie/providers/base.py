from abc import ABC, abstractmethod
from pathlib import Path

from oppie.models.apply import OperationResult
from oppie.models.capabilities import ProviderCapabilities
from oppie.models.operation import Operation
from oppie.models.sync import SyncResult
from oppie.models.ticket import Ticket


class TicketProvider(ABC):
    """Abstract base class for all ticket providers."""

    @property
    @abstractmethod
    def home(self) -> Path:
        """Instance home directory."""

    @property
    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        """Advertise supported features."""

    @abstractmethod
    def read_ticket(self, ticket_id: str) -> Ticket | None:
        """Read a ticket by ID. Return None if not found."""

    @abstractmethod
    def update_ticket(self, ticket_id: str, updates: dict) -> Ticket:
        """Update a ticket's fields. Raise if ticket not found."""

    @abstractmethod
    def list_tickets(self) -> list[Ticket]:
        """List all tickets."""

    def upsert_ticket(self, ticket: Ticket) -> Ticket:
        """Insert or update a ticket. Default: try update, fall back to write.

        Subclasses may override with an optimized implementation.
        """
        existing = self.read_ticket(ticket.id)
        if existing is not None:
            updates = {
                k: v
                for k, v in ticket.to_dict().items()
                if k not in ('id', 'metadata', 'schema_version')
            }
            return self.update_ticket(ticket.id, updates)
        raise NotImplementedError(
            f'{type(self).__name__} does not support creating tickets via upsert'
        )

    def validate_operations(self, operations: list[Operation]) -> list[str]:
        """Validate operations against provider capabilities and ticket existence.

        Check that the provider supports each field update and that
        each ticket and field exists. Return a list of error strings.
        Empty list means all valid.
        """
        errors: list[str] = []
        for op in operations:
            cap_error = self.capabilities.validate_operation(op)
            if cap_error:
                errors.append(f'[{op.ticket_id}.{op.field}] {cap_error}')
                continue

            value_error = self.capabilities.validate_operation_value(op)
            if value_error:
                errors.append(f'[{op.ticket_id}.{op.field}] {value_error}')

            ticket = self.read_ticket(op.ticket_id)
            if ticket is None:
                errors.append(
                    f'[{op.ticket_id}.{op.field}] Ticket not found: {op.ticket_id}'
                )
                continue

            if not hasattr(ticket, op.field):
                errors.append(
                    f'[{op.ticket_id}.{op.field}] Unknown field {op.field!r} on ticket'
                )
        return errors

    def search_tickets(self, query: str) -> list[Ticket]:
        """Search tickets by text query. Default: in-memory title+description match.

        Subclasses may override with a more efficient implementation (e.g., SQLite FTS).
        """
        pattern = query.lower()
        return [
            t
            for t in self.list_tickets()
            if pattern in t.title.lower() or pattern in t.description.lower()
        ]


class ExternalProvider(TicketProvider, ABC):
    """Abstract base class for external ticket providers (Linear, Jira, etc)."""

    @property
    @abstractmethod
    def version(self) -> str:
        """Provider interface version (e.g., 'v1')."""

    @abstractmethod
    def sync(self, checkpoint: str | None = None) -> SyncResult:
        """Sync tickets from external system to local cache."""

    @abstractmethod
    def apply(self, operations: list[Operation]) -> list[OperationResult]:
        """Apply mutations to external system (outbox flush)."""
