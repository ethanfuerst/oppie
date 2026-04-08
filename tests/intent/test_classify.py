from unittest.mock import AsyncMock

import pytest

from oppie.intent import Intent, classify_intent
from oppie.llm.base import LLMResponse, TokenUsage


@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    llm.generate = AsyncMock()
    llm.__aenter__ = AsyncMock(return_value=llm)
    llm.__aexit__ = AsyncMock(return_value=False)
    return llm


@pytest.mark.asyncio
async def test_classifies_question(mock_llm):
    mock_llm.generate.return_value = LLMResponse(
        text='',
        json={'intent': 'question'},
        usage=TokenUsage(10, 5),
    )

    result = await classify_intent('what is blocking?', mock_llm)

    assert result == Intent.QUESTION


@pytest.mark.asyncio
async def test_classifies_instruction(mock_llm):
    mock_llm.generate.return_value = LLMResponse(
        text='',
        json={'intent': 'instruction'},
        usage=TokenUsage(10, 5),
    )

    result = await classify_intent('move bugs to done', mock_llm)

    assert result == Intent.INSTRUCTION


@pytest.mark.asyncio
async def test_classifies_apply(mock_llm):
    mock_llm.generate.return_value = LLMResponse(
        text='',
        json={'intent': 'apply'},
        usage=TokenUsage(10, 5),
    )

    result = await classify_intent('apply it', mock_llm)

    assert result == Intent.APPLY


@pytest.mark.asyncio
async def test_defaults_to_question_on_bad_response(mock_llm):
    mock_llm.generate.return_value = LLMResponse(
        text='garbage',
        json=None,
        usage=TokenUsage(10, 5),
    )

    result = await classify_intent('anything', mock_llm)

    assert result == Intent.QUESTION


@pytest.mark.asyncio
async def test_defaults_to_question_on_invalid_intent(mock_llm):
    mock_llm.generate.return_value = LLMResponse(
        text='',
        json={'intent': 'ambiguous'},
        usage=TokenUsage(10, 5),
    )

    result = await classify_intent('something', mock_llm)

    assert result == Intent.QUESTION


@pytest.mark.asyncio
async def test_schema_has_three_intents(mock_llm):
    mock_llm.generate.return_value = LLMResponse(
        text='',
        json={'intent': 'question'},
        usage=TokenUsage(10, 5),
    )

    await classify_intent('anything', mock_llm)

    call_kwargs = mock_llm.generate.call_args.kwargs
    schema = call_kwargs['response_schema']
    assert schema['properties']['intent']['enum'] == [
        'question',
        'instruction',
        'apply',
    ]
