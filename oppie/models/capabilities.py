from dataclasses import dataclass, field

from oppie.models.operation import Operation


@dataclass(slots=True)
class ProviderCapabilities:
    supports_sync: bool = True
    supports_incremental_sync: bool = False
    supports_write: bool = False
    supports_create: bool = False
    supports_projects: bool = False
    supports_estimates: bool = False
    supports_cycles: bool = False
    supports_custom_fields: bool = False
    supported_field_updates: list[str] = field(default_factory=list)

    def validate_operation(self, op: Operation) -> str | None:
        """Return None if valid, error string if operation not supported."""
        if not self.supports_write:
            return 'Provider does not support write operations'
        if op.field not in self.supported_field_updates:
            return (
                f'Provider does not support updating field {op.field!r}. '
                f'Supported fields: {self.supported_field_updates}'
            )
        return None

    def to_dict(self) -> dict:
        return {
            'supports_sync': self.supports_sync,
            'supports_incremental_sync': self.supports_incremental_sync,
            'supports_write': self.supports_write,
            'supports_create': self.supports_create,
            'supports_projects': self.supports_projects,
            'supports_estimates': self.supports_estimates,
            'supports_cycles': self.supports_cycles,
            'supports_custom_fields': self.supports_custom_fields,
            'supported_field_updates': list(self.supported_field_updates),
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'ProviderCapabilities':
        return cls(**data)
