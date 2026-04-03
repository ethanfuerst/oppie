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
    field_constraints: dict[str, list[str] | None] = field(default_factory=dict)

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

    def validate_operation_value(self, op: Operation) -> str | None:
        """Return None if valid, error string if after_value is not allowed."""
        if op.field not in self.field_constraints:
            return None  # No constraints defined — allow any value
        allowed = self.field_constraints[op.field]
        if allowed is None:
            return None  # Free-form field
        if op.after_value not in allowed:
            return (
                f'Invalid value {op.after_value!r} for field {op.field!r}. '
                f'Allowed: {allowed}'
            )
        return None

    def validate_operation_value_raw(self, field: str, value: object) -> str | None:
        """Return None if valid, error string if value is not allowed for field."""
        if field not in self.supported_field_updates:
            return (
                f'Provider does not support updating field {field!r}. '
                f'Supported fields: {self.supported_field_updates}'
            )
        if field not in self.field_constraints:
            return None
        allowed = self.field_constraints[field]
        if allowed is None:
            return None
        if value not in allowed:
            return f'Invalid value {value!r} for field {field!r}. Allowed: {allowed}'
        return None

    def format_constraints_for_prompt(self) -> str:
        """Format field constraints as a text block for LLM prompts."""
        if not self.field_constraints:
            return ''
        lines = ['Valid fields and allowed values:']
        for field_name, allowed in sorted(self.field_constraints.items()):
            if allowed is None:
                lines.append(f'  - {field_name}: (free-form text)')
            else:
                lines.append(f'  - {field_name}: {", ".join(allowed)}')
        return '\n'.join(lines)

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
            'field_constraints': dict(self.field_constraints),
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'ProviderCapabilities':
        return cls(**data)
