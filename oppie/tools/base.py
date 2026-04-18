from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine
    from pathlib import Path

    from oppie.models.capabilities import ProviderCapabilities
    from oppie.providers.base import TicketProvider


@dataclass(slots=True)
class ToolResult:
    """Result of executing a tool."""

    content: str
    is_error: bool = False


@dataclass(slots=True)
class ToolContext:
    """Shared context passed to all tool executions."""

    provider: TicketProvider
    home: Path
    capabilities: ProviderCapabilities


@dataclass(slots=True)
class Tool:
    """Definition of an LLM-callable tool."""

    name: str
    description: str
    schema: dict[str, Any]
    execute: Callable[[dict, ToolContext], Coroutine[Any, Any, ToolResult]]
    modes: set[str]

    def to_llm_schema(self) -> dict[str, Any]:
        """Return the tool definition for LLM APIs.

        Emits a provider-agnostic dict with keys ``name``, ``description``,
        and ``schema`` (a JSON-Schema object). Adapters translate ``schema``
        to their wire key (``parameters`` for OpenAI, ``input_schema`` for
        Anthropic).
        """
        return {
            'name': self.name,
            'description': self.description,
            'schema': self.schema,
        }
