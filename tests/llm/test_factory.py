from unittest.mock import patch

import pytest

from oppie.config import LLMBackend, LLMConfig
from oppie.llm import LLMNotConfiguredError, create_llm_provider
from oppie.llm.anthropic import AnthropicProvider
from oppie.llm.openai_compatible import OpenAICompatibleProvider


def test_create_openai_compatible_provider():
    config = LLMConfig(backend=LLMBackend.OPENAI_COMPATIBLE, model='gpt-4')
    provider = create_llm_provider(config)

    assert isinstance(provider, OpenAICompatibleProvider)


def test_create_anthropic_provider():
    config = LLMConfig(backend=LLMBackend.ANTHROPIC, model='claude-3')
    provider = create_llm_provider(config)

    assert isinstance(provider, AnthropicProvider)


def test_create_raises_not_configured_for_none():
    with pytest.raises(LLMNotConfiguredError):
        create_llm_provider(None)


def test_create_raises_not_configured_for_non_config():
    with pytest.raises(LLMNotConfiguredError):
        create_llm_provider('invalid')


def test_create_openai_raises_when_httpx_missing():
    config = LLMConfig(backend=LLMBackend.OPENAI_COMPATIBLE, model='gpt-4')
    with (
        patch('oppie.llm.openai_compatible.httpx', None),
        pytest.raises(LLMNotConfiguredError, match=r'oppie\[openai\]'),
    ):
        create_llm_provider(config)


def test_create_anthropic_raises_when_httpx_missing():
    config = LLMConfig(backend=LLMBackend.ANTHROPIC, model='claude-3')
    with (
        patch('oppie.llm.anthropic.httpx', None),
        pytest.raises(LLMNotConfiguredError, match=r'oppie\[anthropic\]'),
    ):
        create_llm_provider(config)
