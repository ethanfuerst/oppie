from unittest.mock import AsyncMock, patch

import pytest

from oppie.llm.base import LLMResponse, TokenUsage
from oppie.models.plan import PlanStatus
from oppie.plan import amend_plan, generate_plan, load_plan
from oppie.plan.engine import PLAN_RESPONSE_SCHEMA
from tests.helpers import make_ticket, write_ticket
from tests.plan_engine.conftest import make_mock_llm


def test_plan_response_schema_is_valid():
    assert PLAN_RESPONSE_SCHEMA['type'] == 'object'
    assert 'operations' in PLAN_RESPONSE_SCHEMA['properties']
    assert 'risks' in PLAN_RESPONSE_SCHEMA['properties']
    assert set(PLAN_RESPONSE_SCHEMA['required']) == {'operations', 'risks'}


@pytest.mark.asyncio
async def test_generate_plan_llm_path(home, provider):
    ticket = make_ticket(ticket_id='T-1', status='open')
    write_ticket(home, ticket)

    response_json = {
        'operations': [
            {
                'ticket_id': 'T-1',
                'field': 'status',
                'before_value': 'open',
                'after_value': 'done',
                'rationale': 'Closing as requested',
            }
        ],
        'risks': ['Ticket may not be ready to close'],
    }
    mock_llm = make_mock_llm(response_json)

    with patch('oppie.plan.engine.create_llm_provider', return_value=mock_llm):
        plan = await generate_plan(provider, None, 'close T-1')

    assert plan.status == PlanStatus.SAVED
    assert len(plan.operations) == 1
    assert plan.operations[0].ticket_id == 'T-1'
    assert plan.operations[0].after_value == 'done'
    assert 'Ticket may not be ready to close' in plan.risks
    assert plan.ticket_snapshots is not None
    assert 'T-1' in plan.ticket_snapshots
    # Verify plan was saved
    loaded = load_plan(home, plan.plan_id)
    assert loaded.plan_id == plan.plan_id


@pytest.mark.asyncio
async def test_generate_plan_llm_no_structured_output(home, provider):
    mock_llm = make_mock_llm(None)
    mock_llm.generate = AsyncMock(
        return_value=LLMResponse(
            text='some text',
            json=None,
            usage=TokenUsage(prompt_tokens=10, completion_tokens=5),
        )
    )

    with (
        patch('oppie.plan.engine.create_llm_provider', return_value=mock_llm),
        pytest.raises(ValueError, match='LLM returned no structured output'),
    ):
        await generate_plan(provider, None, 'do something')


@pytest.mark.asyncio
async def test_generate_plan_fallback_path(home, provider):
    ticket = make_ticket(ticket_id='T-1', status='open')
    write_ticket(home, ticket)

    # No config -> LLMNotConfiguredError -> fallback
    plan = await generate_plan(provider, None, 'close all tickets')

    assert plan.status == PlanStatus.SAVED
    assert any('without LLM' in r for r in plan.risks)
    assert len(plan.operations) == 1
    assert plan.operations[0].field == 'status'
    assert plan.operations[0].after_value == 'done'
    assert plan.ticket_snapshots is not None
    assert 'T-1' in plan.ticket_snapshots


@pytest.mark.asyncio
async def test_generate_plan_fallback_with_preflight_errors(home, provider):
    ticket = make_ticket(ticket_id='T-1', status='open')
    write_ticket(home, ticket)

    def fake_preflight(prov, ops):
        return ['Simulated preflight failure']

    with patch('oppie.plan.engine._run_preflight', side_effect=fake_preflight):
        plan = await generate_plan(provider, None, 'close all tickets')

    assert plan.status == PlanStatus.INVALID
    assert 'Simulated preflight failure' in plan.risks
    assert plan.ticket_snapshots is not None


@pytest.mark.asyncio
async def test_generate_plan_llm_with_preflight_errors(home, provider):
    # No tickets exist, so operations referencing T-MISSING will fail preflight
    response_json = {
        'operations': [
            {
                'ticket_id': 'T-MISSING',
                'field': 'status',
                'before_value': 'open',
                'after_value': 'done',
                'rationale': 'Close it',
            }
        ],
        'risks': [],
    }
    mock_llm = make_mock_llm(response_json)

    with patch('oppie.plan.engine.create_llm_provider', return_value=mock_llm):
        plan = await generate_plan(provider, None, 'close T-MISSING')

    assert plan.status == PlanStatus.INVALID
    assert any('Ticket not found' in r for r in plan.risks)


@pytest.mark.asyncio
async def test_amend_links_parent(home, provider):
    ticket = make_ticket(ticket_id='T-1', status='open')
    write_ticket(home, ticket)

    # Create original plan via fallback
    original = await generate_plan(provider, None, 'close all tickets')

    # Amend it (also via fallback since no config)
    amended = await amend_plan(provider, None, original.plan_id)

    assert amended.parent_plan_id == original.plan_id
    # Amended plan was saved
    loaded = load_plan(home, amended.plan_id)
    assert loaded.parent_plan_id == original.plan_id


@pytest.mark.asyncio
async def test_amend_not_found(home, provider):
    with pytest.raises(FileNotFoundError, match='Plan not found'):
        await amend_plan(provider, None, 'nonexistent')
