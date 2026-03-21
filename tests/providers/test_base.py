import pytest

from oppie.models.apply import ApplyResult
from oppie.models.capabilities import ProviderCapabilities
from oppie.models.operation import Operation
from oppie.models.sync import SyncResult
from oppie.providers.base import ExternalProvider


def test_external_provider_cannot_be_instantiated():
    with pytest.raises(TypeError):
        ExternalProvider()


def test_concrete_provider_implements_interface():
    class FakeProvider(ExternalProvider):
        @property
        def version(self) -> str:
            return 'v1'

        @property
        def capabilities(self) -> ProviderCapabilities:
            return ProviderCapabilities()

        def sync(self, checkpoint: str | None = None) -> SyncResult:
            return SyncResult(tickets_upserted=0)

        def apply(self, operations: list[Operation]) -> ApplyResult:
            return ApplyResult(
                apply_id='a1',
                plan_id='p1',
                results=[],
                duration=0.0,
                created_at='2026-01-01T00:00:00Z',
            )

    provider = FakeProvider()

    assert provider.version == 'v1'
    assert provider.capabilities.supports_sync is True
