from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass


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


@dataclass(slots=True)
class LLMResponse:
    text: str
    json: dict | None
    usage: TokenUsage

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
        max_tokens: int = 2000,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Send messages and return the full response."""

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
