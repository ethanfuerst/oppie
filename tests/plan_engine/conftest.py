from unittest.mock import AsyncMock

from oppie.llm.base import LLMResponse, TokenUsage, ToolCallRequest


def make_mock_llm(response_text='', tool_calls=None, stop_reason='end_turn'):
    """Create a mock LLMProvider for engine tests."""
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(
        return_value=LLMResponse(
            text=response_text,
            json=None,
            usage=TokenUsage(prompt_tokens=100, completion_tokens=50),
            tool_calls=tool_calls or [],
            stop_reason=stop_reason,
        )
    )
    mock_llm.__aenter__ = AsyncMock(return_value=mock_llm)
    mock_llm.__aexit__ = AsyncMock(return_value=None)
    return mock_llm


def make_plan_mock_llm(operations_data):
    """Create a mock LLM that simulates the 3-step plan engine flow.

    Step 1 (research): no tool calls
    Step 2 (propose): one propose_operation tool call per operation
    Step 3 (summary): text-only response

    operations_data is a list of dicts like:
    [{'ticket_id': 'T-1', 'field': 'status', 'new_value': 'done', 'rationale': 'close it'}]
    """
    # Step 1: research - no tool calls
    research_response = LLMResponse(
        text='',
        json=None,
        usage=TokenUsage(80, 20),
        tool_calls=[],
        stop_reason='end_turn',
    )

    # Step 2: propose - tool calls for each operation
    propose_tool_calls = [
        ToolCallRequest(
            id=f'tc-{i}',
            name='propose_operation',
            input=op,
        )
        for i, op in enumerate(operations_data)
    ]
    propose_response = LLMResponse(
        text='',
        json=None,
        usage=TokenUsage(100, 80),
        tool_calls=propose_tool_calls,
        stop_reason='tool_use',
    )
    # After tool results, no more calls
    propose_done = LLMResponse(
        text='',
        json=None,
        usage=TokenUsage(50, 20),
        tool_calls=[],
        stop_reason='end_turn',
    )

    # Step 3: summary
    summary_response = LLMResponse(
        text='Plan complete.',
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
    mock_llm.__aenter__ = AsyncMock(return_value=mock_llm)
    mock_llm.__aexit__ = AsyncMock(return_value=None)
    return mock_llm
