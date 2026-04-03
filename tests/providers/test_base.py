from pathlib import Path

import pytest

from oppie.models.apply import OperationResult
from oppie.models.capabilities import ProviderCapabilities
from oppie.models.operation import Operation
from oppie.models.sync import SyncResult
from oppie.models.ticket import Ticket
from oppie.providers.base import ExternalProvider
from tests.helpers import make_ticket


def test_external_provider_cannot_be_instantiated():
    with pytest.raises(TypeError):
        ExternalProvider()


def test_concrete_provider_implements_interface(tmp_path):
    class FakeProvider(ExternalProvider):
        @property
        def home(self) -> Path:
            return tmp_path

        @property
        def version(self) -> str:
            return 'v1'

        @property
        def capabilities(self) -> ProviderCapabilities:
            return ProviderCapabilities()

        def read_ticket(self, ticket_id: str) -> Ticket | None:
            return None

        def update_ticket(self, ticket_id: str, updates: dict) -> Ticket:
            raise NotImplementedError

        def list_tickets(self) -> list[Ticket]:
            return []

        def sync(self, checkpoint: str | None = None) -> SyncResult:
            return SyncResult(tickets_upserted=0)

        def apply(self, operations: list[Operation]) -> list[OperationResult]:
            return []

    provider = FakeProvider()

    assert provider.version == 'v1'
    assert provider.capabilities.supports_sync is True


def test_search_tickets_default_filters_by_title(home, provider):
    provider.create_ticket(make_ticket(ticket_id='T-1', title='Fix login bug'))
    provider.create_ticket(make_ticket(ticket_id='T-2', title='Add dashboard'))

    results = provider.search_tickets('login')

    assert len(results) == 1
    assert results[0].id == 'T-1'
