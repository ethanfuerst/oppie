from unittest.mock import AsyncMock

from oppie.llm.base import LLMResponse, TokenUsage


def make_mock_llm(response_json):
    """Create a mock LLMProvider that returns a canned response."""
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(
        return_value=LLMResponse(
            text='',
            json=response_json,
            usage=TokenUsage(prompt_tokens=100, completion_tokens=50),
        )
    )
    mock_llm.__aenter__ = AsyncMock(return_value=mock_llm)
    mock_llm.__aexit__ = AsyncMock(return_value=None)
    return mock_llm
