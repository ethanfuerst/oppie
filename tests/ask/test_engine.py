from unittest.mock import AsyncMock, patch

import pytest

from oppie.ask.engine import AskResult, _generate_fallback, generate_ask
from oppie.config import (
    InstanceType,
    LLMBackend,
    LLMConfig,
    OppieConfig,
    ProviderConfig,
)
from oppie.llm import LLMNotConfiguredError
from oppie.llm.base import LLMResponse, TokenUsage
from oppie.providers.local import LocalProvider
from tests.helpers import make_ticket, setup_instance, write_ticket


@pytest.fixture
def home(tmp_path):
    return setup_instance(tmp_path)


@pytest.fixture
def provider(home):
    return LocalProvider.setup(home)


def test_fallback_filters_by_status():
    tickets = [
        make_ticket(ticket_id='T-1', status='blocked'),
        make_ticket(ticket_id='T-2', status='open'),
    ]

    result = _generate_fallback(tickets, 'what is blocked?')

    assert 'T-1' in result
    assert 'T-2' not in result


def test_fallback_no_match():
    tickets = [make_ticket(ticket_id='T-1', status='open')]

    result = _generate_fallback(tickets, 'what is blocked?')

    assert 'No tickets found' in result


def test_fallback_filters_by_priority():
    tickets = [
        make_ticket(ticket_id='T-1', priority='urgent'),
        make_ticket(ticket_id='T-2', priority='low'),
    ]

    result = _generate_fallback(tickets, 'what urgent tickets are there?')

    assert 'T-1' in result
    assert 'T-2' not in result


def test_fallback_includes_tip():
    tickets = [make_ticket(ticket_id='T-1', status='open')]

    result = _generate_fallback(tickets, 'what is open?')

    assert 'Configure an LLM' in result


@pytest.mark.asyncio
async def test_generate_ask_no_llm(home, provider):
    write_ticket(home, make_ticket(ticket_id='T-1', status='open'))

    with patch(
        'oppie.ask.engine.create_llm_provider', side_effect=LLMNotConfiguredError()
    ):
        result = await generate_ask(provider, None, 'what is open?')

    assert isinstance(result, AskResult)
    assert 'T-1' in result.answer
    assert result.artifact_path is not None
    assert result.usage is None


@pytest.mark.asyncio
async def test_generate_ask_with_llm(home, provider):
    write_ticket(home, make_ticket(ticket_id='T-1', status='open'))

    config = OppieConfig(
        instance_type=InstanceType.REPO,
        provider=ProviderConfig(type='local'),
        llm=LLMConfig(backend=LLMBackend.OPENAI_COMPATIBLE, model='test'),
    )

    # Ask engine runs 2 steps: research (no tool calls) -> answer (text)
    research_response = LLMResponse(
        text='',
        json=None,
        usage=TokenUsage(80, 20),
        tool_calls=[],
        stop_reason='end_turn',
    )
    answer_response = LLMResponse(
        text='The answer is 42.',
        json=None,
        usage=TokenUsage(100, 50),
        tool_calls=[],
        stop_reason='end_turn',
    )

    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(side_effect=[research_response, answer_response])
    mock_llm.__aenter__ = AsyncMock(return_value=mock_llm)
    mock_llm.__aexit__ = AsyncMock(return_value=False)

    with patch('oppie.ask.engine.create_llm_provider', return_value=mock_llm):
        result = await generate_ask(provider, config, 'what is open?')

    assert result.answer == 'The answer is 42.'
    assert result.usage is not None
    assert result.usage.prompt_tokens == 180
    assert result.usage.completion_tokens == 70
