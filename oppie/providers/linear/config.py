from pydantic import Field

from oppie.config import ProviderConfig, ProviderType


class LinearProviderConfig(ProviderConfig):
    """Linear-specific provider configuration."""

    provider_type: ProviderType = Field(default=ProviderType.LINEAR, alias='type')
    team_id: str
    project_id: str | None = None
    sync_statuses: list[str] | None = None
    sync_labels: list[str] | None = None
