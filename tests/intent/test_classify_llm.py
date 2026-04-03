from unittest.mock import AsyncMock

import pytest

from oppie.intent import Intent, classify_intent_llm
from oppie.llm.base import LLMResponse, TokenUsage


@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    llm.generate = AsyncMock()
    llm.__aenter__ = AsyncMock(return_value=llm)
    llm.__aexit__ = AsyncMock(return_value=False)
    return llm


@pytest.mark.asyncio
async def test_llm_classifies_question(mock_llm):
    mock_llm.generate.return_value = LLMResponse(
        text='',
        json={'intent': 'question'},
        usage=TokenUsage(10, 5),
    )

    result = await classify_intent_llm('what is blocking?', mock_llm)

    assert result == Intent.QUESTION


@pytest.mark.asyncio
async def test_llm_classifies_instruction(mock_llm):
    mock_llm.generate.return_value = LLMResponse(
        text='',
        json={'intent': 'instruction'},
        usage=TokenUsage(10, 5),
    )

    result = await classify_intent_llm('move bugs to done', mock_llm)

    assert result == Intent.INSTRUCTION


@pytest.mark.asyncio
async def test_llm_falls_back_on_bad_response(mock_llm):
    mock_llm.generate.return_value = LLMResponse(
        text='garbage',
        json=None,
        usage=TokenUsage(10, 5),
    )

    result = await classify_intent_llm('what is blocking?', mock_llm)

    # Falls back to local heuristics — question mark present
    assert result == Intent.QUESTION
