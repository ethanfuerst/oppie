import json
from unittest.mock import AsyncMock, patch

import pytest

from oppie.llm.base import LLMResponse, TokenUsage
from oppie.models.operation import Operation
from oppie.models.plan import Plan, PlanStatus
from oppie.models.ticket import Ticket, TicketMetadata, TicketSource
from oppie.plan import (
    PLAN_INDEX_FILENAME,
    PLAN_RESPONSE_SCHEMA,
    amend_plan,
    find_similar_plans,
    generate_plan,
    generate_plan_fallback,
    load_context,
    load_plan,
    run_preflight,
    save_plan,
)
from oppie.providers.local import LocalProvider


def _setup_instance(tmp_path):
    """Create minimal instance directory structure."""
    for d in ['tickets', 'context', 'artifacts/plans', 'state', 'logs']:
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    return tmp_path


def _make_ticket(ticket_id, status='open', priority='medium', labels=None):
    return Ticket(
        id=ticket_id,
        title=f'Ticket {ticket_id}',
        status=status,
        priority=priority,
        owner='alice',
        labels=labels or [],
        created_at='2026-01-01T00:00:00Z',
        updated_at='2026-01-01T00:00:00Z',
        project='proj',
        description=f'Description for {ticket_id}',
        metadata=TicketMetadata(source=TicketSource.LOCAL),
    )


def _write_ticket(home, ticket):
    """Write a ticket JSON file to the instance."""
    path = home / 'tickets' / f'{ticket.id}.json'
    path.write_text(json.dumps(ticket.to_dict(), indent=2) + '\n')


# --- load_context ---


def test_load_context_reads_existing_files(tmp_path):
    home = _setup_instance(tmp_path)
    (home / 'context' / 'vision.md').write_text('Our vision statement.')
    (home / 'context' / 'roadmap.md').write_text('Q1 goals.')

    result = load_context(home)

    assert result == {'vision': 'Our vision statement.', 'roadmap': 'Q1 goals.'}


def test_load_context_skips_missing_files(tmp_path):
    home = _setup_instance(tmp_path)
    (home / 'context' / 'vision.md').write_text('Vision only.')

    result = load_context(home)

    assert result == {'vision': 'Vision only.'}


def test_load_context_skips_empty_files(tmp_path):
    home = _setup_instance(tmp_path)
    (home / 'context' / 'vision.md').write_text('')
    (home / 'context' / 'roadmap.md').write_text('  ')

    result = load_context(home)

    assert result == {}


def test_load_context_no_context_dir(tmp_path):
    result = load_context(tmp_path)

    assert result == {}


# --- find_similar_plans ---


def test_find_similar_plans_matches_by_keyword_overlap(tmp_path):
    home = _setup_instance(tmp_path)
    plan = Plan(
        plan_id='aaa11111',
        instruction='close all security bugs',
        operations=[],
        risks=[],
        created_at='2026-01-01T00:00:00Z',
        status=PlanStatus.SAVED,
    )
    save_plan(plan, home)

    result = find_similar_plans(home, 'close security tickets')

    assert len(result) == 1
    assert result[0].plan_id == 'aaa11111'


def test_find_similar_plans_returns_empty_for_no_overlap(tmp_path):
    home = _setup_instance(tmp_path)
    plan = Plan(
        plan_id='bbb22222',
        instruction='deploy infrastructure',
        operations=[],
        risks=[],
        created_at='2026-01-01T00:00:00Z',
        status=PlanStatus.SAVED,
    )
    save_plan(plan, home)

    result = find_similar_plans(home, 'close all bugs')

    assert result == []


def test_find_similar_plans_respects_limit(tmp_path):
    home = _setup_instance(tmp_path)
    for i in range(5):
        plan = Plan(
            plan_id=f'plan{i:04d}',
            instruction=f'close bug number {i}',
            operations=[],
            risks=[],
            created_at='2026-01-01T00:00:00Z',
            status=PlanStatus.SAVED,
        )
        save_plan(plan, home)

    result = find_similar_plans(home, 'close bug', limit=2)

    assert len(result) == 2


def test_find_similar_plans_rebuilds_index_when_missing(tmp_path):
    home = _setup_instance(tmp_path)
    plan = Plan(
        plan_id='ccc33333',
        instruction='close all bugs',
        operations=[],
        risks=[],
        created_at='2026-01-01T00:00:00Z',
        status=PlanStatus.SAVED,
    )
    # Write plan JSON directly without index
    plan_path = home / 'artifacts' / 'plans' / 'plan-ccc33333.json'
    plan_path.write_text(json.dumps(plan.to_dict(), indent=2))

    result = find_similar_plans(home, 'close bugs')

    assert len(result) == 1
    assert result[0].plan_id == 'ccc33333'
    # Verify index was rebuilt
    assert (home / 'artifacts' / 'plans' / PLAN_INDEX_FILENAME).exists()


def test_find_similar_plans_skips_malformed_index_entries(tmp_path):
    home = _setup_instance(tmp_path)
    plan = Plan(
        plan_id='ddd44444',
        instruction='close bugs',
        operations=[],
        risks=[],
        created_at='2026-01-01T00:00:00Z',
        status=PlanStatus.SAVED,
    )
    save_plan(plan, home)
    # Append a malformed line to the index
    index_path = home / 'artifacts' / 'plans' / PLAN_INDEX_FILENAME
    with open(index_path, 'a') as f:
        f.write('not valid json\n')

    result = find_similar_plans(home, 'close bugs')

    assert len(result) == 1


# --- generate_plan_fallback ---


def test_fallback_generates_status_operations(tmp_path):
    home = _setup_instance(tmp_path)
    ticket = _make_ticket(ticket_id='T-1', status='open')
    _write_ticket(home, ticket)
    provider = LocalProvider(home)

    plan = generate_plan_fallback('close all tickets', provider)

    assert plan.status == PlanStatus.SAVED
    assert len(plan.operations) == 1
    assert plan.operations[0].field == 'status'
    assert plan.operations[0].after_value == 'done'
    assert plan.operations[0].before_value == 'open'
    provider.close()


def test_fallback_generates_priority_operations(tmp_path):
    home = _setup_instance(tmp_path)
    ticket = _make_ticket(ticket_id='T-2', priority='low')
    _write_ticket(home, ticket)
    provider = LocalProvider(home)

    plan = generate_plan_fallback('prioritize these tickets', provider)

    assert len(plan.operations) == 1
    assert plan.operations[0].field == 'priority'
    assert plan.operations[0].after_value == 'high'
    provider.close()


def test_fallback_skips_tickets_already_in_target_state(tmp_path):
    home = _setup_instance(tmp_path)
    ticket = _make_ticket(ticket_id='T-3', status='done')
    _write_ticket(home, ticket)
    provider = LocalProvider(home)

    plan = generate_plan_fallback('close everything', provider)

    assert plan.operations == []
    provider.close()


def test_fallback_filters_by_label_keywords(tmp_path):
    home = _setup_instance(tmp_path)
    t1 = _make_ticket(ticket_id='T-1', status='open', labels=['security'])
    t2 = _make_ticket(ticket_id='T-2', status='open', labels=['docs'])
    _write_ticket(home, t1)
    _write_ticket(home, t2)
    provider = LocalProvider(home)

    plan = generate_plan_fallback('close security tickets', provider)

    ticket_ids = [op.ticket_id for op in plan.operations]

    assert 'T-1' in ticket_ids
    assert 'T-2' not in ticket_ids
    provider.close()


def test_fallback_no_matching_keywords(tmp_path):
    home = _setup_instance(tmp_path)
    ticket = _make_ticket(ticket_id='T-1', status='open')
    _write_ticket(home, ticket)
    provider = LocalProvider(home)

    plan = generate_plan_fallback('do something vague', provider)

    assert plan.operations == []
    assert 'without LLM' in plan.risks[0]
    provider.close()


def test_fallback_includes_no_llm_risk(tmp_path):
    home = _setup_instance(tmp_path)
    provider = LocalProvider(home)

    plan = generate_plan_fallback('close things', provider)

    assert any('without LLM' in r for r in plan.risks)
    provider.close()


# --- run_preflight ---


def test_preflight_valid_operations(tmp_path):
    home = _setup_instance(tmp_path)
    ticket = _make_ticket(ticket_id='T-1', status='open')
    _write_ticket(home, ticket)
    provider = LocalProvider(home)
    op = Operation('T-1', 'status', 'wrong_before', 'done', 'closing')

    errors = run_preflight([op], provider)

    assert errors == []
    assert op.before_value == 'open'  # overwritten with actual value
    provider.close()


def test_preflight_ticket_not_found(tmp_path):
    home = _setup_instance(tmp_path)
    provider = LocalProvider(home)
    op = Operation('MISSING-1', 'status', 'open', 'done', 'closing')

    errors = run_preflight([op], provider)

    assert len(errors) == 1
    assert 'Ticket not found' in errors[0]
    provider.close()


def test_preflight_unsupported_field(tmp_path):
    home = _setup_instance(tmp_path)
    ticket = _make_ticket(ticket_id='T-1')
    _write_ticket(home, ticket)
    provider = LocalProvider(home)
    op = Operation('T-1', 'nonexistent_field', None, 'val', 'test')

    errors = run_preflight([op], provider)

    assert len(errors) == 1
    assert 'does not support updating field' in errors[0]
    provider.close()


def test_preflight_protected_field(tmp_path):
    home = _setup_instance(tmp_path)
    ticket = _make_ticket(ticket_id='T-1')
    _write_ticket(home, ticket)
    provider = LocalProvider(home)
    op = Operation('T-1', 'id', 'T-1', 'T-999', 'rename')

    errors = run_preflight([op], provider)

    assert len(errors) == 1
    provider.close()


def test_preflight_multiple_errors(tmp_path):
    home = _setup_instance(tmp_path)
    provider = LocalProvider(home)
    ops = [
        Operation('MISSING', 'status', 'open', 'done', 'close'),
        Operation('ALSO-MISSING', 'status', 'open', 'done', 'close'),
    ]

    errors = run_preflight(ops, provider)

    assert len(errors) == 2
    provider.close()


# --- save_plan / load_plan ---


def test_save_and_load_plan(tmp_path):
    home = _setup_instance(tmp_path)
    plan = Plan(
        plan_id='abcd1234',
        instruction='close bugs',
        operations=[
            Operation('T-1', 'status', 'open', 'done', 'closing'),
        ],
        risks=['some risk'],
        created_at='2026-01-01T00:00:00Z',
        status=PlanStatus.SAVED,
    )

    path = save_plan(plan, home)

    assert path.exists()
    assert path.name == 'plan-abcd1234.json'

    loaded = load_plan('abcd1234', home)

    assert loaded.plan_id == plan.plan_id
    assert loaded.instruction == plan.instruction
    assert len(loaded.operations) == 1
    assert loaded.operations[0].ticket_id == 'T-1'
    assert loaded.status == PlanStatus.SAVED


def test_load_plan_not_found(tmp_path):
    home = _setup_instance(tmp_path)

    with pytest.raises(FileNotFoundError, match='Plan not found'):
        load_plan('nonexistent', home)


def test_save_plan_with_parent_plan_id(tmp_path):
    home = _setup_instance(tmp_path)
    plan = Plan(
        plan_id='child123',
        instruction='re-close bugs',
        operations=[],
        risks=[],
        created_at='2026-01-01T00:00:00Z',
        status=PlanStatus.SAVED,
        parent_plan_id='parent99',
    )

    save_plan(plan, home)
    loaded = load_plan('child123', home)

    assert loaded.parent_plan_id == 'parent99'


# --- PLAN_RESPONSE_SCHEMA ---


def test_plan_response_schema_is_valid():
    assert PLAN_RESPONSE_SCHEMA['type'] == 'object'
    assert 'operations' in PLAN_RESPONSE_SCHEMA['properties']
    assert 'risks' in PLAN_RESPONSE_SCHEMA['properties']
    assert set(PLAN_RESPONSE_SCHEMA['required']) == {'operations', 'risks'}


# --- generate_plan (async) ---


def _make_mock_llm(response_json):
    """Create a mock LLMProvider that returns a canned response."""
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(
        return_value=LLMResponse(
            text='',
            json=response_json,
            usage=TokenUsage(prompt_tokens=100, completion_tokens=50),
        )
    )
    mock_llm.__aenter__ = AsyncMock(return_value=mock_llm)
    mock_llm.__aexit__ = AsyncMock(return_value=None)
    return mock_llm


@pytest.mark.asyncio
async def test_generate_plan_llm_path(tmp_path):
    home = _setup_instance(tmp_path)
    ticket = _make_ticket(ticket_id='T-1', status='open')
    _write_ticket(home, ticket)

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
    mock_llm = _make_mock_llm(response_json)

    with patch('oppie.plan.engine.create_llm_provider', return_value=mock_llm):
        plan = await generate_plan('close T-1', home)

    assert plan.status == PlanStatus.SAVED
    assert len(plan.operations) == 1
    assert plan.operations[0].ticket_id == 'T-1'
    assert plan.operations[0].after_value == 'done'
    assert 'Ticket may not be ready to close' in plan.risks
    # Verify plan was saved
    loaded = load_plan(plan.plan_id, home)
    assert loaded.plan_id == plan.plan_id


@pytest.mark.asyncio
async def test_generate_plan_llm_no_structured_output(tmp_path):
    home = _setup_instance(tmp_path)
    mock_llm = _make_mock_llm(None)
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
        await generate_plan('do something', home)


@pytest.mark.asyncio
async def test_generate_plan_fallback_path(tmp_path):
    home = _setup_instance(tmp_path)
    ticket = _make_ticket(ticket_id='T-1', status='open')
    _write_ticket(home, ticket)

    # No config → LLMNotConfiguredError → fallback
    plan = await generate_plan('close all tickets', home)

    assert plan.status == PlanStatus.SAVED
    assert any('without LLM' in r for r in plan.risks)
    assert len(plan.operations) == 1
    assert plan.operations[0].field == 'status'
    assert plan.operations[0].after_value == 'done'


@pytest.mark.asyncio
async def test_generate_plan_llm_with_preflight_errors(tmp_path):
    home = _setup_instance(tmp_path)
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
    mock_llm = _make_mock_llm(response_json)

    with patch('oppie.plan.engine.create_llm_provider', return_value=mock_llm):
        plan = await generate_plan('close T-MISSING', home)

    assert plan.status == PlanStatus.INVALID
    assert any('Ticket not found' in r for r in plan.risks)


# --- amend_plan (async) ---


@pytest.mark.asyncio
async def test_amend_plan_links_parent(tmp_path):
    home = _setup_instance(tmp_path)
    ticket = _make_ticket(ticket_id='T-1', status='open')
    _write_ticket(home, ticket)

    # Create original plan via fallback
    original = await generate_plan('close all tickets', home)

    # Amend it (also via fallback since no config)
    amended = await amend_plan(original.plan_id, home)

    assert amended.parent_plan_id == original.plan_id
    # Amended plan was saved
    loaded = load_plan(amended.plan_id, home)
    assert loaded.parent_plan_id == original.plan_id


@pytest.mark.asyncio
async def test_amend_plan_not_found(tmp_path):
    home = _setup_instance(tmp_path)

    with pytest.raises(FileNotFoundError, match='Plan not found'):
        await amend_plan('nonexistent', home)
