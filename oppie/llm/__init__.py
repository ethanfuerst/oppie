from __future__ import annotations

from typing import TYPE_CHECKING

from oppie.llm.base import (
    LLMNotConfiguredError,
    LLMProvider,
    LLMResponse,
    StreamResult,
    TokenUsage,
)

if TYPE_CHECKING:
    from oppie.config import LLMConfig


def create_llm_provider(
    config: LLMConfig | None,
) -> LLMProvider:
    """Construct the appropriate LLM provider from config.

    Raise LLMNotConfiguredError if config is None.
    """
    from oppie.config import LLMBackend, LLMConfig

    if not isinstance(config, LLMConfig):
        raise LLMNotConfiguredError('LLM is not configured')

    try:
        if config.backend == LLMBackend.OPENAI_COMPATIBLE:
            from oppie.llm.openai_compatible import OpenAICompatibleProvider

            return OpenAICompatibleProvider(
                model=config.model,
                endpoint=config.endpoint or 'http://localhost:8080/v1',
            )
        elif config.backend == LLMBackend.ANTHROPIC:
            from oppie.llm.anthropic import AnthropicProvider

            return AnthropicProvider(
                model=config.model,
                endpoint=config.endpoint,
            )
        else:
            raise ValueError(f'Unknown LLM backend: {config.backend}')
    except ImportError as exc:
        raise LLMNotConfiguredError(str(exc)) from exc


__all__ = [
    'LLMNotConfiguredError',
    'LLMProvider',
    'LLMResponse',
    'StreamResult',
    'TokenUsage',
    'create_llm_provider',
]
