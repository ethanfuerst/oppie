from unittest.mock import patch

import pytest

from oppie.models.plan import PlanStatus
from oppie.plan import amend_plan, generate_plan, load_plan
from tests.helpers import make_ticket, write_ticket
from tests.plan_engine.conftest import make_plan_mock_llm


@pytest.mark.asyncio
async def test_generate_plan_llm_path(home, provider):
    ticket = make_ticket(ticket_id='T-1', status='open')
    write_ticket(home, ticket)

    mock_llm = make_plan_mock_llm(
        [
            {
                'ticket_id': 'T-1',
                'field': 'status',
                'new_value': 'done',
                'rationale': 'Closing as requested',
            }
        ]
    )

    with patch('oppie.plan.engine.create_llm_provider', return_value=mock_llm):
        plan = await generate_plan(provider, None, 'close T-1')

    assert plan.status == PlanStatus.SAVED
    assert len(plan.operations) == 1
    assert plan.operations[0].ticket_id == 'T-1'
    assert plan.operations[0].after_value == 'done'
    assert plan.ticket_snapshots is not None
    assert 'T-1' in plan.ticket_snapshots
    loaded = load_plan(home, plan.plan_id)
    assert loaded.plan_id == plan.plan_id


@pytest.mark.asyncio
async def test_generate_plan_fallback_path(home, provider):
    ticket = make_ticket(ticket_id='T-1', status='open')
    write_ticket(home, ticket)

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
    # No tickets exist so propose_operation for T-MISSING will produce an error tool result
    # But since the tool validates during execution, the operation won't be collected
    # and the plan will have no operations (preflight won't find errors either)
    mock_llm = make_plan_mock_llm(
        [
            {
                'ticket_id': 'T-MISSING',
                'field': 'status',
                'new_value': 'done',
                'rationale': 'Close it',
            }
        ]
    )

    with patch('oppie.plan.engine.create_llm_provider', return_value=mock_llm):
        plan = await generate_plan(provider, None, 'close T-MISSING')

    # propose_operation returns is_error=True for missing ticket, so no operations collected
    assert len(plan.operations) == 0


@pytest.mark.asyncio
async def test_amend_links_parent(home, provider):
    ticket = make_ticket(ticket_id='T-1', status='open')
    write_ticket(home, ticket)

    original = await generate_plan(provider, None, 'close all tickets')
    amended = await amend_plan(provider, None, original.plan_id)

    assert amended.parent_plan_id == original.plan_id
    loaded = load_plan(home, amended.plan_id)
    assert loaded.parent_plan_id == original.plan_id


@pytest.mark.asyncio
async def test_amend_not_found(home, provider):
    with pytest.raises(FileNotFoundError, match='Plan not found'):
        await amend_plan(provider, None, 'nonexistent')
