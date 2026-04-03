import json
from unittest.mock import AsyncMock

import pytest

from oppie.engine import EngineMode, run_engine
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


@pytest.mark.asyncio
async def test_ask_mode_runs_research_then_answer(tool_context):
    """Ask mode runs two steps: research then answer."""
    research_response = LLMResponse(
        text='',
        json=None,
        usage=TokenUsage(80, 20),
        tool_calls=[],
        stop_reason='end_turn',
    )
    answer_response = LLMResponse(
        text='There are 0 open tickets.',
        json=None,
        usage=TokenUsage(100, 50),
        tool_calls=[],
        stop_reason='end_turn',
    )
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(side_effect=[research_response, answer_response])

    result = await run_engine(
        prompt='how many tickets are open?',
        tools=[SEARCH_TICKETS_TOOL, GET_TICKET_TOOL],
        llm=mock_llm,
        tool_context=tool_context,
        mode=EngineMode.ASK,
        system_prompt='You are oppie.',
    )

    assert result.text == 'There are 0 open tickets.'
    assert result.operations == []
    assert result.turns == 2
    assert mock_llm.generate.call_count == 2


@pytest.mark.asyncio
async def test_plan_mode_runs_three_steps(home, tool_context):
    """Plan mode runs research -> propose -> summary."""
    provider = LocalProvider(home)
    provider.create_ticket(make_ticket(ticket_id='T-1', status='open'))
    tool_context.provider = provider

    # Step 1 (research): no tool calls, just stops
    research_response = LLMResponse(
        text='',
        json=None,
        usage=TokenUsage(80, 20),
        tool_calls=[],
        stop_reason='end_turn',
    )
    # Step 2 (propose): forced propose_operation call
    propose_response = LLMResponse(
        text='',
        json=None,
        usage=TokenUsage(100, 80),
        tool_calls=[
            ToolCallRequest(
                id='tc-1',
                name='propose_operation',
                input={
                    'ticket_id': 'T-1',
                    'field': 'status',
                    'new_value': 'done',
                    'rationale': 'closing it',
                },
            )
        ],
        stop_reason='tool_use',
    )
    # Step 2 continued: after tool result, no more calls
    propose_done = LLMResponse(
        text='',
        json=None,
        usage=TokenUsage(50, 20),
        tool_calls=[],
        stop_reason='end_turn',
    )
    # Step 3 (summary): text only
    summary_response = LLMResponse(
        text='Closed T-1.',
        json=None,
        usage=TokenUsage(60, 30),
        tool_calls=[],
        stop_reason='end_turn',
    )
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(
        side_effect=[
            research_response,
            propose_response,
            propose_done,
            summary_response,
        ]
    )

    result = await run_engine(
        prompt='close T-1',
        tools=[SEARCH_TICKETS_TOOL, GET_TICKET_TOOL, PROPOSE_OPERATION_TOOL],
        llm=mock_llm,
        tool_context=tool_context,
        mode=EngineMode.PLAN,
        system_prompt='You are oppie.',
    )

    assert len(result.operations) == 1
    assert result.operations[0].ticket_id == 'T-1'
    assert result.operations[0].after_value == 'done'
    assert result.text == 'Closed T-1.'
    assert mock_llm.generate.call_count == 4


@pytest.mark.asyncio
async def test_engine_aggregates_token_usage(tool_context):
    """Token usage is summed across all steps."""
    r1 = LLMResponse(text='', json=None, usage=TokenUsage(100, 50), tool_calls=[])
    r2 = LLMResponse(
        text='answer', json=None, usage=TokenUsage(200, 100), tool_calls=[]
    )
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(side_effect=[r1, r2])

    result = await run_engine(
        prompt='question',
        tools=[SEARCH_TICKETS_TOOL, GET_TICKET_TOOL],
        llm=mock_llm,
        tool_context=tool_context,
        mode=EngineMode.ASK,
        system_prompt='test',
    )

    assert result.usage.prompt_tokens == 300
    assert result.usage.completion_tokens == 150


@pytest.mark.asyncio
async def test_ask_research_step_calls_search_tickets(home, tool_context):
    """Research step dispatches search_tickets tool call and feeds result back."""
    provider = LocalProvider(home)
    provider.create_ticket(make_ticket(ticket_id='T-1', status='open'))
    provider.create_ticket(make_ticket(ticket_id='T-2', status='done'))
    tool_context.provider = provider

    # Research turn 1: LLM calls search_tickets
    search_call = LLMResponse(
        text='',
        json=None,
        usage=TokenUsage(80, 30),
        tool_calls=[
            ToolCallRequest(
                id='tc-search',
                name='search_tickets',
                input={'status': 'open'},
            )
        ],
        stop_reason='tool_use',
    )
    # Research turn 2: LLM stops after seeing results
    research_done = LLMResponse(
        text='',
        json=None,
        usage=TokenUsage(60, 20),
        tool_calls=[],
        stop_reason='end_turn',
    )
    # Answer step
    answer = LLMResponse(
        text='There is 1 open ticket: T-1.',
        json=None,
        usage=TokenUsage(100, 50),
        tool_calls=[],
        stop_reason='end_turn',
    )
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(side_effect=[search_call, research_done, answer])

    result = await run_engine(
        prompt='how many tickets are open?',
        tools=[SEARCH_TICKETS_TOOL, GET_TICKET_TOOL],
        llm=mock_llm,
        tool_context=tool_context,
        mode=EngineMode.ASK,
        system_prompt='You are oppie.',
    )

    assert result.text == 'There is 1 open ticket: T-1.'
    assert mock_llm.generate.call_count == 3
    # Verify the tool result was passed back in messages (before the inject_prompt)
    second_call_messages = mock_llm.generate.call_args_list[1][1]['messages']
    tool_results_msg = [
        m for m in second_call_messages if m.get('role') == 'tool_results'
    ]
    assert len(tool_results_msg) == 1
    tool_content = json.loads(tool_results_msg[0]['results'][0]['content'])
    assert len(tool_content) == 1
    assert tool_content[0]['id'] == 'T-1'


@pytest.mark.asyncio
async def test_ask_research_step_calls_get_ticket(home, tool_context):
    """Research step dispatches get_ticket and returns full ticket details."""
    provider = LocalProvider(home)
    provider.create_ticket(make_ticket(ticket_id='T-5', status='blocked'))
    tool_context.provider = provider

    # Research turn 1: LLM calls get_ticket
    get_call = LLMResponse(
        text='',
        json=None,
        usage=TokenUsage(70, 25),
        tool_calls=[
            ToolCallRequest(
                id='tc-get',
                name='get_ticket',
                input={'ticket_id': 'T-5'},
            )
        ],
        stop_reason='tool_use',
    )
    # Research turn 2: done
    research_done = LLMResponse(
        text='',
        json=None,
        usage=TokenUsage(50, 15),
        tool_calls=[],
        stop_reason='end_turn',
    )
    # Answer step
    answer = LLMResponse(
        text='T-5 is blocked.',
        json=None,
        usage=TokenUsage(80, 40),
        tool_calls=[],
        stop_reason='end_turn',
    )
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(side_effect=[get_call, research_done, answer])

    result = await run_engine(
        prompt='what is the status of T-5?',
        tools=[SEARCH_TICKETS_TOOL, GET_TICKET_TOOL],
        llm=mock_llm,
        tool_context=tool_context,
        mode=EngineMode.ASK,
        system_prompt='You are oppie.',
    )

    assert result.text == 'T-5 is blocked.'
    # Verify get_ticket result was sent back
    second_call_messages = mock_llm.generate.call_args_list[1][1]['messages']
    tool_results_msg = [
        m for m in second_call_messages if m.get('role') == 'tool_results'
    ]
    assert len(tool_results_msg) == 1
    tool_content = json.loads(tool_results_msg[0]['results'][0]['content'])
    assert tool_content['id'] == 'T-5'
    assert tool_content['status'] == 'blocked'


@pytest.mark.asyncio
async def test_plan_research_step_multi_turn(home, tool_context):
    """Plan research step calls search_tickets then get_ticket across turns."""
    provider = LocalProvider(home)
    provider.create_ticket(make_ticket(ticket_id='T-1', status='open'))
    tool_context.provider = provider

    # Research turn 1: search
    search_call = LLMResponse(
        text='',
        json=None,
        usage=TokenUsage(80, 30),
        tool_calls=[
            ToolCallRequest(id='tc-s', name='search_tickets', input={'status': 'open'})
        ],
        stop_reason='tool_use',
    )
    # Research turn 2: get_ticket for details
    get_call = LLMResponse(
        text='',
        json=None,
        usage=TokenUsage(70, 25),
        tool_calls=[
            ToolCallRequest(id='tc-g', name='get_ticket', input={'ticket_id': 'T-1'})
        ],
        stop_reason='tool_use',
    )
    # Research turn 3: done
    research_done = LLMResponse(
        text='',
        json=None,
        usage=TokenUsage(50, 15),
        tool_calls=[],
        stop_reason='end_turn',
    )
    # Propose step
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
                    'rationale': 'close it',
                },
            )
        ],
        stop_reason='tool_use',
    )
    propose_done = LLMResponse(
        text='',
        json=None,
        usage=TokenUsage(40, 10),
        tool_calls=[],
        stop_reason='end_turn',
    )
    # Summary step
    summary = LLMResponse(
        text='Closed T-1.',
        json=None,
        usage=TokenUsage(60, 30),
        tool_calls=[],
        stop_reason='end_turn',
    )
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(
        side_effect=[
            search_call,
            get_call,
            research_done,
            propose,
            propose_done,
            summary,
        ]
    )

    result = await run_engine(
        prompt='close open tickets',
        tools=[SEARCH_TICKETS_TOOL, GET_TICKET_TOOL, PROPOSE_OPERATION_TOOL],
        llm=mock_llm,
        tool_context=tool_context,
        mode=EngineMode.PLAN,
        system_prompt='You are oppie.',
    )

    assert len(result.operations) == 1
    assert result.operations[0].ticket_id == 'T-1'
    assert result.text == 'Closed T-1.'
    assert mock_llm.generate.call_count == 6
