from unittest.mock import AsyncMock, patch

import pytest

from oppie.llm.base import LLMResponse, TokenUsage
from oppie.plan.engine import generate_plan
from oppie.providers.local import LocalProvider
from tests.helpers import make_ticket, setup_instance, write_ticket


@pytest.fixture
def home(tmp_path):
    return setup_instance(tmp_path)


@pytest.fixture
def provider(home):
    return LocalProvider.setup(home)


def _make_llm_response(operations, risks=None):
    """Build an LLMResponse with structured JSON output."""
    return LLMResponse(
        text='plan response',
        json={'operations': operations, 'risks': risks or []},
        usage=TokenUsage(100, 50),
    )


@pytest.mark.asyncio
async def test_generate_plan_retries_on_invalid_values(home, provider):
    """generate_plan retries when LLM produces invalid field values."""
    write_ticket(home, make_ticket(ticket_id='T-1', status='open'))

    # First response: invalid status value
    bad_response = _make_llm_response(
        [
            {
                'ticket_id': 'T-1',
                'field': 'status',
                'before_value': 'open',
                'after_value': 'banana',
                'rationale': 'oops',
            }
        ]
    )
    # Second response: valid status value
    good_response = _make_llm_response(
        [
            {
                'ticket_id': 'T-1',
                'field': 'status',
                'before_value': 'open',
                'after_value': 'done',
                'rationale': 'close it',
            }
        ]
    )

    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(side_effect=[bad_response, good_response])
    mock_llm.__aenter__ = AsyncMock(return_value=mock_llm)
    mock_llm.__aexit__ = AsyncMock(return_value=False)

    with patch('oppie.plan.engine.create_llm_provider', return_value=mock_llm):
        plan = await generate_plan(provider, None, 'close T-1', save=False)

    assert len(plan.operations) == 1
    assert plan.operations[0].after_value == 'done'
    assert mock_llm.generate.call_count == 2


@pytest.mark.asyncio
async def test_generate_plan_gives_up_after_max_retries(home, provider):
    """generate_plan stops retrying after MAX_RETRIES and returns plan with errors."""
    write_ticket(home, make_ticket(ticket_id='T-1', status='open'))

    # All responses produce invalid values
    bad_response = _make_llm_response(
        [
            {
                'ticket_id': 'T-1',
                'field': 'status',
                'before_value': 'open',
                'after_value': 'banana',
                'rationale': 'oops',
            }
        ]
    )

    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(return_value=bad_response)
    mock_llm.__aenter__ = AsyncMock(return_value=mock_llm)
    mock_llm.__aexit__ = AsyncMock(return_value=False)

    with patch('oppie.plan.engine.create_llm_provider', return_value=mock_llm):
        plan = await generate_plan(provider, None, 'close T-1', save=False)

    # 1 initial + 2 retries = 3 calls
    assert mock_llm.generate.call_count == 3
    # Plan still has the invalid value but risks include the validation errors
    assert plan.operations[0].after_value == 'banana'
