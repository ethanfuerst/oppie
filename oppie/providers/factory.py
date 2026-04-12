from __future__ import annotations

from typing import TYPE_CHECKING

from oppie.config import ProviderType

if TYPE_CHECKING:
    from pathlib import Path

    from oppie.config import OppieConfig
    from oppie.providers.base import ExternalProvider, TicketProvider


def create_external_provider(
    config: OppieConfig, home: Path, cache: TicketProvider
) -> ExternalProvider:
    """Construct the configured external provider.

    Raises ValueError if the configured provider is not external (e.g., LOCAL).
    """
    provider_type = config.provider.provider_type
    if provider_type == ProviderType.LINEAR:
        from oppie.providers.linear import LinearProvider
        from oppie.providers.linear.config import LinearProviderConfig

        assert isinstance(config.provider, LinearProviderConfig)
        return LinearProvider(home=home, cache=cache, config=config.provider)
    raise ValueError(
        f'No external provider available for provider_type={provider_type.value!r}'
    )
