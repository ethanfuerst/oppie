from abc import ABC, abstractmethod

from oppie.models.apply import ApplyResult
from oppie.models.capabilities import ProviderCapabilities
from oppie.models.operation import Operation
from oppie.models.sync import SyncResult


class ExternalProvider(ABC):
    """Abstract base class for external ticket providers (Linear, Jira, etc)."""

    @property
    @abstractmethod
    def version(self) -> str:
        """Provider interface version (e.g., 'v1')."""

    @property
    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        """Advertise supported features."""

    @abstractmethod
    def sync(self, checkpoint: str | None = None) -> SyncResult:
        """Sync tickets from external system to local cache."""

    @abstractmethod
    def apply(self, operations: list[Operation]) -> ApplyResult:
        """Apply mutations to external system (called when flushing outbox)."""
