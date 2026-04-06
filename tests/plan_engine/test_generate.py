from unittest.mock import patch

import pytest

from oppie.config import (
    InstanceType,
    LLMBackend,
    LLMConfig,
    OppieConfig,
    ProviderConfig,
)
from oppie.llm import LLMNotConfiguredError
from oppie.models.plan import PlanStatus
from oppie.plan import amend_plan, generate_plan, load_plan
from tests.helpers import make_ticket, write_ticket
from tests.plan_engine.conftest import make_plan_mock_llm

PLAN_TEST_CONFIG = OppieConfig(
    instance_type=InstanceType.REPO,
    provider=ProviderConfig(type='local'),
    llm=LLMConfig(backend=LLMBackend.OPENAI_COMPATIBLE, model='test'),
)


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
        plan = await generate_plan(provider, PLAN_TEST_CONFIG, 'close T-1')

    assert plan.status == PlanStatus.SAVED
    assert len(plan.operations) == 1
    assert plan.operations[0].ticket_id == 'T-1'
    assert plan.operations[0].after_value == 'done'
    assert plan.ticket_snapshots is not None
    assert 'T-1' in plan.ticket_snapshots
    loaded = load_plan(home, plan.plan_id)
    assert loaded.plan_id == plan.plan_id


@pytest.mark.asyncio
async def test_generate_plan_llm_with_preflight_errors(home, provider):
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
        plan = await generate_plan(provider, PLAN_TEST_CONFIG, 'close T-MISSING')

    assert len(plan.operations) == 0


@pytest.mark.asyncio
async def test_generate_plan_no_llm_raises(home, provider):
    with (
        patch(
            'oppie.plan.engine.create_llm_provider',
            side_effect=LLMNotConfiguredError('not configured'),
        ),
        pytest.raises(LLMNotConfiguredError),
    ):
        await generate_plan(provider, PLAN_TEST_CONFIG, 'close all tickets')


@pytest.mark.asyncio
async def test_amend_links_parent(home, provider):
    ticket = make_ticket(ticket_id='T-1', status='open')
    write_ticket(home, ticket)

    mock_llm = make_plan_mock_llm(
        [
            {
                'ticket_id': 'T-1',
                'field': 'status',
                'new_value': 'done',
                'rationale': 'close',
            }
        ]
    )

    with patch('oppie.plan.engine.create_llm_provider', return_value=mock_llm):
        original = await generate_plan(provider, PLAN_TEST_CONFIG, 'close all tickets')

    mock_llm_2 = make_plan_mock_llm(
        [
            {
                'ticket_id': 'T-1',
                'field': 'status',
                'new_value': 'done',
                'rationale': 'close',
            }
        ]
    )
    with patch('oppie.plan.engine.create_llm_provider', return_value=mock_llm_2):
        amended = await amend_plan(provider, PLAN_TEST_CONFIG, original.plan_id)

    assert amended.parent_plan_id == original.plan_id
    loaded = load_plan(home, amended.plan_id)
    assert loaded.parent_plan_id == original.plan_id


@pytest.mark.asyncio
async def test_amend_not_found(home, provider):
    with pytest.raises(FileNotFoundError, match='Plan not found'):
        await amend_plan(provider, PLAN_TEST_CONFIG, 'nonexistent')
