from unittest.mock import patch

import pytest

from oppie.llm.anthropic import AnthropicProvider
from oppie.llm.openai_compatible import OpenAICompatibleProvider


def test_openai_provider_raises_when_httpx_missing():
    with (
        patch('oppie.llm.openai_compatible.httpx', None),
        pytest.raises(ImportError, match='pip install oppie\\[llm\\]'),
    ):
        OpenAICompatibleProvider(model='gpt-4')


def test_anthropic_provider_raises_when_httpx_missing():
    with (
        patch('oppie.llm.anthropic.httpx', None),
        pytest.raises(ImportError, match='pip install oppie\\[llm\\]'),
    ):
        AnthropicProvider(model='claude-3')
