from unittest.mock import AsyncMock, patch

import pytest

from oppie.ask.engine import generate_ask
from oppie.config import (
    InstanceType,
    LLMBackend,
    LLMConfig,
    OppieConfig,
    ProviderConfig,
)
from oppie.events import AskResultEvent, StatsEvent, StepStartEvent
from oppie.llm import LLMNotConfiguredError
from oppie.llm.base import LLMResponse, TokenUsage
from oppie.providers.local import LocalProvider
from tests.helpers import make_ticket, setup_instance, write_ticket

_TEST_CONFIG = OppieConfig(
    instance_type=InstanceType.REPO,
    provider=ProviderConfig(type='local'),
    llm=LLMConfig(backend=LLMBackend.OPENAI_COMPATIBLE, model='test'),
)


@pytest.fixture
def home(tmp_path):
    return setup_instance(tmp_path)


@pytest.fixture
def provider(home):
    return LocalProvider.setup(home)


def _mock_stream_result(text: str, usage: TokenUsage | None = None):
    """Create a mock StreamResult that yields chunks of text."""
    chunks = list(text)

    class MockStreamResult:
        def __init__(self):
            self.usage = usage

        def __aiter__(self):
            return self

        async def __anext__(self):
            if chunks:
                return chunks.pop(0)
            raise StopAsyncIteration

    return MockStreamResult()


@pytest.mark.asyncio
async def test_generate_ask_with_llm(home, provider):
    write_ticket(home, make_ticket(ticket_id='T-1', status='open'))

    # Ask engine runs 2 steps: research (no tool calls) -> answer (streamed)
    research_response = LLMResponse(
        text='',
        json=None,
        usage=TokenUsage(80, 20),
        tool_calls=[],
        stop_reason='end_turn',
    )

    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(side_effect=[research_response])
    mock_llm.stream = AsyncMock(
        return_value=_mock_stream_result('The answer is 42.', TokenUsage(100, 50))
    )
    mock_llm.__aenter__ = AsyncMock(return_value=mock_llm)
    mock_llm.__aexit__ = AsyncMock(return_value=False)

    events = []
    with patch('oppie.ask.engine.create_llm_provider', return_value=mock_llm):
        async for event in generate_ask(provider, _TEST_CONFIG, 'what is open?'):
            events.append(event)

    result_events = [e for e in events if isinstance(e, AskResultEvent)]

    assert len(result_events) == 1
    result = result_events[0].result
    assert result.answer == 'The answer is 42.'
    assert result.usage is not None
    assert result.usage.prompt_tokens == 180
    assert result.usage.completion_tokens == 70


@pytest.mark.asyncio
async def test_generate_ask_no_llm_raises(home, provider):
    write_ticket(home, make_ticket(ticket_id='T-1', status='open'))

    with (
        patch(
            'oppie.ask.engine.create_llm_provider',
            side_effect=LLMNotConfiguredError('not configured'),
        ),
        pytest.raises(LLMNotConfiguredError),
    ):
        async for _event in generate_ask(provider, _TEST_CONFIG, 'what is open?'):
            pass


@pytest.mark.asyncio
async def test_generate_ask_yields_events(home, provider):
    write_ticket(home, make_ticket(ticket_id='T-1', status='open'))

    research_response = LLMResponse(
        text='', json=None, usage=TokenUsage(80, 20), tool_calls=[]
    )

    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(side_effect=[research_response])
    mock_llm.stream = AsyncMock(
        return_value=_mock_stream_result('Answer.', TokenUsage(100, 50))
    )
    mock_llm.__aenter__ = AsyncMock(return_value=mock_llm)
    mock_llm.__aexit__ = AsyncMock(return_value=False)

    events = []
    with patch('oppie.ask.engine.create_llm_provider', return_value=mock_llm):
        async for event in generate_ask(provider, _TEST_CONFIG, 'question'):
            events.append(event)

    step_starts = [e for e in events if isinstance(e, StepStartEvent)]
    stats = [e for e in events if isinstance(e, StatsEvent)]

    assert [s.step_name for s in step_starts] == ['research', 'answer']
    assert len(stats) == 1
    assert isinstance(events[-1], AskResultEvent)
