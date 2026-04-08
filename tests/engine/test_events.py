from unittest.mock import AsyncMock

import pytest

from oppie.engine import EngineMode, run_engine
from oppie.events import (
    PlanOperationEvent,
    StatsEvent,
    StepStartEvent,
    TextDeltaEvent,
    ThinkingEvent,
    ToolCallEvent,
)
from oppie.llm.base import LLMResponse, TokenUsage, ToolCallRequest
from oppie.providers.local import LocalProvider
from oppie.tools.base import ToolContext
from oppie.tools.operations import PROPOSE_OPERATION_TOOL
from oppie.tools.tickets import GET_TICKET_TOOL, SEARCH_TICKETS_TOOL
from tests.helpers import make_ticket, setup_instance


@pytest.fixture
def home(tmp_path):
    return setup_instance(tmp_path)


@pytest.fixture
def tool_context(home):
    provider = LocalProvider(home)
    return ToolContext(provider=provider, home=home, capabilities=provider.capabilities)


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
async def test_ask_events_order(tool_context):
    """Ask mode emits events in correct order: step_start, thinking, text_delta."""
    research_response = LLMResponse(
        text='', json=None, usage=TokenUsage(80, 20), tool_calls=[]
    )
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(side_effect=[research_response])
    mock_llm.stream = AsyncMock(
        return_value=_mock_stream_result('answer', TokenUsage(100, 50))
    )

    events = [
        e
        async for e in run_engine(
            prompt='question',
            tools=[SEARCH_TICKETS_TOOL, GET_TICKET_TOOL],
            llm=mock_llm,
            tool_context=tool_context,
            mode=EngineMode.ASK,
            system_prompt='test',
        )
    ]

    step_starts = [e for e in events if isinstance(e, StepStartEvent)]

    assert [s.step_name for s in step_starts] == ['research', 'answer']


@pytest.mark.asyncio
async def test_plan_events_step_order(home, tool_context):
    """Plan mode emits StepStartEvents for research, propose, summary."""
    provider = LocalProvider(home)
    provider.create_ticket(make_ticket(ticket_id='T-1', status='open'))
    tool_context.provider = provider

    research = LLMResponse(text='', json=None, usage=TokenUsage(80, 20), tool_calls=[])
    propose = LLMResponse(
        text='',
        json=None,
        usage=TokenUsage(100, 60),
        tool_calls=[
            ToolCallRequest(
                id='tc-p',
                name='propose_operation',
                input={
                    'ticket_id': 'T-1',
                    'field': 'status',
                    'new_value': 'done',
                    'rationale': 'close',
                },
            )
        ],
        stop_reason='tool_use',
    )
    propose_done = LLMResponse(
        text='', json=None, usage=TokenUsage(40, 10), tool_calls=[]
    )
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(side_effect=[research, propose, propose_done])
    mock_llm.stream = AsyncMock(
        return_value=_mock_stream_result('Summary.', TokenUsage(60, 30))
    )

    events = [
        e
        async for e in run_engine(
            prompt='close T-1',
            tools=[SEARCH_TICKETS_TOOL, GET_TICKET_TOOL, PROPOSE_OPERATION_TOOL],
            llm=mock_llm,
            tool_context=tool_context,
            mode=EngineMode.PLAN,
            system_prompt='test',
        )
    ]

    step_starts = [e for e in events if isinstance(e, StepStartEvent)]

    assert [s.step_name for s in step_starts] == ['research', 'propose', 'summary']


@pytest.mark.asyncio
async def test_plan_events_include_operations(home, tool_context):
    """Plan mode emits PlanOperationEvent for accepted operations."""
    provider = LocalProvider(home)
    provider.create_ticket(make_ticket(ticket_id='T-1', status='open'))
    tool_context.provider = provider

    research = LLMResponse(text='', json=None, usage=TokenUsage(80, 20), tool_calls=[])
    propose = LLMResponse(
        text='',
        json=None,
        usage=TokenUsage(100, 60),
        tool_calls=[
            ToolCallRequest(
                id='tc-p',
                name='propose_operation',
                input={
                    'ticket_id': 'T-1',
                    'field': 'status',
                    'new_value': 'done',
                    'rationale': 'close',
                },
            )
        ],
        stop_reason='tool_use',
    )
    propose_done = LLMResponse(
        text='', json=None, usage=TokenUsage(40, 10), tool_calls=[]
    )
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(side_effect=[research, propose, propose_done])
    mock_llm.stream = AsyncMock(
        return_value=_mock_stream_result('Done.', TokenUsage(60, 30))
    )

    events = [
        e
        async for e in run_engine(
            prompt='close T-1',
            tools=[SEARCH_TICKETS_TOOL, GET_TICKET_TOOL, PROPOSE_OPERATION_TOOL],
            llm=mock_llm,
            tool_context=tool_context,
            mode=EngineMode.PLAN,
            system_prompt='test',
        )
    ]

    op_events = [e for e in events if isinstance(e, PlanOperationEvent)]

    assert len(op_events) == 1
    assert op_events[0].operation.ticket_id == 'T-1'
    assert op_events[0].operation.after_value == 'done'


@pytest.mark.asyncio
async def test_tool_call_events_emitted(home, tool_context):
    """ToolCallEvent is emitted for each tool call dispatched."""
    provider = LocalProvider(home)
    provider.create_ticket(make_ticket(ticket_id='T-1', status='open'))
    tool_context.provider = provider

    search_call = LLMResponse(
        text='',
        json=None,
        usage=TokenUsage(80, 30),
        tool_calls=[
            ToolCallRequest(id='tc-s', name='search_tickets', input={'status': 'open'})
        ],
        stop_reason='tool_use',
    )
    research_done = LLMResponse(
        text='', json=None, usage=TokenUsage(60, 20), tool_calls=[]
    )
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(side_effect=[search_call, research_done])
    mock_llm.stream = AsyncMock(
        return_value=_mock_stream_result('answer', TokenUsage(100, 50))
    )

    events = [
        e
        async for e in run_engine(
            prompt='how many open?',
            tools=[SEARCH_TICKETS_TOOL, GET_TICKET_TOOL],
            llm=mock_llm,
            tool_context=tool_context,
            mode=EngineMode.ASK,
            system_prompt='test',
        )
    ]

    tc_events = [e for e in events if isinstance(e, ToolCallEvent)]

    assert len(tc_events) == 1
    assert tc_events[0].tool_name == 'search_tickets'


@pytest.mark.asyncio
async def test_text_delta_events_from_stream(tool_context):
    """Text-only step yields TextDeltaEvent chunks via stream()."""
    research = LLMResponse(text='', json=None, usage=TokenUsage(80, 20), tool_calls=[])
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(side_effect=[research])
    mock_llm.stream = AsyncMock(
        return_value=_mock_stream_result(
            'There are 0 open tickets.', TokenUsage(100, 50)
        )
    )

    events = [
        e
        async for e in run_engine(
            prompt='how many open?',
            tools=[SEARCH_TICKETS_TOOL, GET_TICKET_TOOL],
            llm=mock_llm,
            tool_context=tool_context,
            mode=EngineMode.ASK,
            system_prompt='test',
        )
    ]

    text_events = [e for e in events if isinstance(e, TextDeltaEvent)]

    assert len(text_events) > 0
    full_text = ''.join(e.text for e in text_events)
    assert full_text == 'There are 0 open tickets.'


@pytest.mark.asyncio
async def test_thinking_event_per_llm_call(tool_context):
    """ThinkingEvent is emitted once per LLM call."""
    research = LLMResponse(text='', json=None, usage=TokenUsage(80, 20), tool_calls=[])
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(side_effect=[research])
    mock_llm.stream = AsyncMock(
        return_value=_mock_stream_result('answer', TokenUsage(100, 50))
    )

    events = [
        e
        async for e in run_engine(
            prompt='question',
            tools=[SEARCH_TICKETS_TOOL, GET_TICKET_TOOL],
            llm=mock_llm,
            tool_context=tool_context,
            mode=EngineMode.ASK,
            system_prompt='test',
        )
    ]

    thinking_events = [e for e in events if isinstance(e, ThinkingEvent)]

    # 1 for research generate(), 1 for answer stream()
    assert len(thinking_events) == 2


@pytest.mark.asyncio
async def test_stats_event_is_last(tool_context):
    """StatsEvent is always the last event yielded."""
    research = LLMResponse(text='', json=None, usage=TokenUsage(80, 20), tool_calls=[])
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(side_effect=[research])
    mock_llm.stream = AsyncMock(
        return_value=_mock_stream_result('answer', TokenUsage(100, 50))
    )

    events = [
        e
        async for e in run_engine(
            prompt='question',
            tools=[SEARCH_TICKETS_TOOL, GET_TICKET_TOOL],
            llm=mock_llm,
            tool_context=tool_context,
            mode=EngineMode.ASK,
            system_prompt='test',
        )
    ]

    assert isinstance(events[-1], StatsEvent)
