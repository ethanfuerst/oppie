from pydantic import Field

from oppie.config import ProviderConfig, ProviderType


class LinearProviderConfig(ProviderConfig):
    """Linear-specific provider configuration."""

    provider_type: ProviderType = Field(default=ProviderType.LINEAR, alias='type')
    team_id: str
    project_id: str | None = None
    sync_statuses: list[str] | None = None
    sync_labels: list[str] | None = None

    def to_dict(self) -> dict:
        """Serialize for oppie.yaml. Include scope fields, exclude api_key."""
        d: dict = {'type': self.provider_type.value, 'team_id': self.team_id}
        if self.project_id:
            d['project_id'] = self.project_id
        if self.sync_statuses:
            d['sync_statuses'] = self.sync_statuses
        if self.sync_labels:
            d['sync_labels'] = self.sync_labels
        return d
