from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field


@dataclass(slots=True)
class TokenUsage:
    prompt_tokens: int
    completion_tokens: int

    def to_dict(self) -> dict[str, int]:
        return {
            'prompt_tokens': self.prompt_tokens,
            'completion_tokens': self.completion_tokens,
        }

    @classmethod
    def from_dict(cls, data: dict[str, int]) -> 'TokenUsage':
        return cls(
            prompt_tokens=data['prompt_tokens'],
            completion_tokens=data['completion_tokens'],
        )

    def __add__(self, other: 'TokenUsage') -> 'TokenUsage':
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
        )


@dataclass(slots=True)
class ToolCallRequest:
    """A tool call requested by the LLM."""

    id: str
    name: str
    input: dict


@dataclass(slots=True)
class ToolCallResult:
    """Result of executing a tool call, sent back to the LLM."""

    request: ToolCallRequest
    content: str
    is_error: bool = False


@dataclass(slots=True)
class LLMResponse:
    text: str
    json: dict | None
    usage: TokenUsage
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    stop_reason: str = 'end_turn'

    def to_dict(self) -> dict:
        return {
            'text': self.text,
            'json': self.json,
            'usage': self.usage.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'LLMResponse':
        return cls(
            text=data['text'],
            json=data.get('json'),
            usage=TokenUsage.from_dict(data['usage']),
        )


class StreamResult:
    """Wraps an async text chunk iterator with post-iteration token usage."""

    def __init__(self, iterator: AsyncIterator[str]) -> None:
        self._iterator = iterator
        self.usage: TokenUsage | None = None

    def __aiter__(self) -> 'StreamResult':
        return self

    async def __anext__(self) -> str:
        return await self._iterator.__anext__()


class LLMNotConfiguredError(Exception):
    """Raised when attempting to construct an LLM provider with no LLM config."""


class LLMProvider(ABC):
    """Abstract base class for LLM backends."""

    @abstractmethod
    async def generate(
        self,
        messages: list[dict],
        response_schema: dict | None = None,
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        system_parts: list[dict] | None = None,
    ) -> LLMResponse:
        """Send messages and return the full response.

        If tools is provided, the LLM may return tool_calls instead of text.
        tool_choice controls forcing: None (auto), 'any' (must call a tool),
        or {'name': 'tool_name'} (must call that specific tool).

        system_parts, when provided, is a list of dicts with 'content' and
        optional 'cache_control' keys. Providers that support structured
        system prompts (e.g. Anthropic) use these instead of the flat
        system string extracted from messages.
        """

    @abstractmethod
    async def stream(
        self,
        messages: list[dict],
        max_tokens: int = 2000,
        temperature: float = 0.7,
    ) -> StreamResult:
        """Send messages and return a streaming result."""

    @abstractmethod
    async def test_connection(self) -> bool:
        """Test connectivity to the LLM backend. Return True if reachable."""

    async def close(self) -> None:  # noqa: B027
        """Close the underlying HTTP client. Override in subclasses."""

    async def __aenter__(self) -> 'LLMProvider':
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
