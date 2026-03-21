import json
from unittest.mock import AsyncMock, patch

import pytest

from oppie.llm.base import LLMResponse, TokenUsage
from oppie.models.operation import Operation
from oppie.models.plan import Plan, PlanStatus
from oppie.plan import PlanEngine
from oppie.providers.local import LocalProvider
from tests.helpers import make_ticket, setup_instance, write_ticket

# --- _load_context ---


def test_load_context_reads_existing_files(plan_engine):
    home = plan_engine._home
    (home / 'context' / 'vision.md').write_text('Our vision statement.')
    (home / 'context' / 'roadmap.md').write_text('Q1 goals.')

    result = plan_engine._load_context()

    assert result == {'vision': 'Our vision statement.', 'roadmap': 'Q1 goals.'}


def test_load_context_skips_missing_files(plan_engine):
    home = plan_engine._home
    (home / 'context' / 'vision.md').write_text('Vision only.')

    result = plan_engine._load_context()

    assert result == {'vision': 'Vision only.'}


def test_load_context_skips_empty_files(plan_engine):
    home = plan_engine._home
    (home / 'context' / 'vision.md').write_text('')
    (home / 'context' / 'roadmap.md').write_text('  ')

    result = plan_engine._load_context()

    assert result == {}


def test_load_context_no_context_dir(tmp_path):
    home = setup_instance(tmp_path)
    # Remove the context dir that setup_instance creates
    (home / 'context').rmdir()
    provider = LocalProvider(home)
    engine = PlanEngine(home, provider)

    result = engine._load_context()

    assert result == {}
    provider.close()


# --- _find_similar_plans ---


def test_find_similar_plans_matches_by_keyword_overlap(plan_engine):
    plan = Plan(
        plan_id='aaa11111',
        instruction='close all security bugs',
        operations=[],
        risks=[],
        created_at='2026-01-01T00:00:00Z',
        status=PlanStatus.SAVED,
    )
    plan_engine.save_plan(plan)

    result = plan_engine._find_similar_plans('close security tickets')

    assert len(result) == 1
    assert result[0].plan_id == 'aaa11111'


def test_find_similar_plans_returns_empty_for_no_overlap(plan_engine):
    plan = Plan(
        plan_id='bbb22222',
        instruction='deploy infrastructure',
        operations=[],
        risks=[],
        created_at='2026-01-01T00:00:00Z',
        status=PlanStatus.SAVED,
    )
    plan_engine.save_plan(plan)

    result = plan_engine._find_similar_plans('close all bugs')

    assert result == []


def test_find_similar_plans_respects_limit(plan_engine):
    for i in range(5):
        plan = Plan(
            plan_id=f'plan{i:04d}',
            instruction=f'close bug number {i}',
            operations=[],
            risks=[],
            created_at='2026-01-01T00:00:00Z',
            status=PlanStatus.SAVED,
        )
        plan_engine.save_plan(plan)

    result = plan_engine._find_similar_plans('close bug', limit=2)

    assert len(result) == 2


def test_find_similar_plans_rebuilds_index_when_missing(plan_engine):
    home = plan_engine._home
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

    result = plan_engine._find_similar_plans('close bugs')

    assert len(result) == 1
    assert result[0].plan_id == 'ccc33333'
    # Verify index was rebuilt
    assert (home / 'artifacts' / 'plans' / PlanEngine.PLAN_INDEX_FILENAME).exists()


def test_find_similar_plans_skips_malformed_index_entries(plan_engine):
    home = plan_engine._home
    plan = Plan(
        plan_id='ddd44444',
        instruction='close bugs',
        operations=[],
        risks=[],
        created_at='2026-01-01T00:00:00Z',
        status=PlanStatus.SAVED,
    )
    plan_engine.save_plan(plan)
    # Append a malformed line to the index
    index_path = home / 'artifacts' / 'plans' / PlanEngine.PLAN_INDEX_FILENAME
    with open(index_path, 'a') as f:
        f.write('not valid json\n')

    result = plan_engine._find_similar_plans('close bugs')

    assert len(result) == 1


# --- _generate_fallback ---


def test_fallback_generates_status_operations(plan_engine):
    ticket = make_ticket(ticket_id='T-1', status='open')
    write_ticket(plan_engine._home, ticket)

    plan = plan_engine._generate_fallback('close all tickets')

    assert plan.status == PlanStatus.SAVED
    assert len(plan.operations) == 1
    assert plan.operations[0].field == 'status'
    assert plan.operations[0].after_value == 'done'
    assert plan.operations[0].before_value == 'open'


def test_fallback_generates_priority_operations(plan_engine):
    ticket = make_ticket(ticket_id='T-2', priority='low')
    write_ticket(plan_engine._home, ticket)

    plan = plan_engine._generate_fallback('prioritize these tickets')

    assert len(plan.operations) == 1
    assert plan.operations[0].field == 'priority'
    assert plan.operations[0].after_value == 'high'


def test_fallback_skips_tickets_already_in_target_state(plan_engine):
    ticket = make_ticket(ticket_id='T-3', status='done')
    write_ticket(plan_engine._home, ticket)

    plan = plan_engine._generate_fallback('close everything')

    assert plan.operations == []


def test_fallback_filters_by_label_keywords(plan_engine):
    t1 = make_ticket(ticket_id='T-1', status='open', labels=['security'])
    t2 = make_ticket(ticket_id='T-2', status='open', labels=['docs'])
    write_ticket(plan_engine._home, t1)
    write_ticket(plan_engine._home, t2)

    plan = plan_engine._generate_fallback('close security tickets')

    ticket_ids = [op.ticket_id for op in plan.operations]

    assert 'T-1' in ticket_ids
    assert 'T-2' not in ticket_ids


def test_fallback_no_matching_keywords(plan_engine):
    ticket = make_ticket(ticket_id='T-1', status='open')
    write_ticket(plan_engine._home, ticket)

    plan = plan_engine._generate_fallback('do something vague')

    assert plan.operations == []
    assert 'without LLM' in plan.risks[0]


def test_fallback_includes_no_llm_risk(plan_engine):
    plan = plan_engine._generate_fallback('close things')

    assert any('without LLM' in r for r in plan.risks)


# --- validate_operations ---


def test_validate_operations_valid(plan_engine):
    ticket = make_ticket(ticket_id='T-1', status='open')
    write_ticket(plan_engine._home, ticket)
    op = Operation('T-1', 'status', 'wrong_before', 'done', 'closing')

    errors = plan_engine._provider.validate_operations([op])

    assert errors == []
    assert op.before_value == 'wrong_before'  # NOT overwritten


def test_validate_operations_ticket_not_found(plan_engine):
    op = Operation('MISSING-1', 'status', 'open', 'done', 'closing')

    errors = plan_engine._provider.validate_operations([op])

    assert len(errors) == 1
    assert 'Ticket not found' in errors[0]


def test_validate_operations_unsupported_field(plan_engine):
    ticket = make_ticket(ticket_id='T-1')
    write_ticket(plan_engine._home, ticket)
    op = Operation('T-1', 'nonexistent_field', None, 'val', 'test')

    errors = plan_engine._provider.validate_operations([op])

    assert len(errors) == 1
    assert 'does not support updating field' in errors[0]


# --- _run_preflight ---


def test_preflight_valid_operations(plan_engine):
    ticket = make_ticket(ticket_id='T-1', status='open')
    write_ticket(plan_engine._home, ticket)
    op = Operation('T-1', 'status', 'wrong_before', 'done', 'closing')

    errors = plan_engine._run_preflight([op])

    assert errors == []
    assert op.before_value == 'open'  # overwritten with actual value


def test_preflight_ticket_not_found(plan_engine):
    op = Operation('MISSING-1', 'status', 'open', 'done', 'closing')

    errors = plan_engine._run_preflight([op])

    assert len(errors) == 1
    assert 'Ticket not found' in errors[0]


def test_preflight_unsupported_field(plan_engine):
    ticket = make_ticket(ticket_id='T-1')
    write_ticket(plan_engine._home, ticket)
    op = Operation('T-1', 'nonexistent_field', None, 'val', 'test')

    errors = plan_engine._run_preflight([op])

    assert len(errors) == 1
    assert 'does not support updating field' in errors[0]


def test_preflight_protected_field(plan_engine):
    ticket = make_ticket(ticket_id='T-1')
    write_ticket(plan_engine._home, ticket)
    op = Operation('T-1', 'id', 'T-1', 'T-999', 'rename')

    errors = plan_engine._run_preflight([op])

    assert len(errors) == 1


def test_preflight_multiple_errors(plan_engine):
    ops = [
        Operation('MISSING', 'status', 'open', 'done', 'close'),
        Operation('ALSO-MISSING', 'status', 'open', 'done', 'close'),
    ]

    errors = plan_engine._run_preflight(ops)

    assert len(errors) == 2


# --- save_plan / load_plan ---


def test_save_and_load_plan(plan_engine):
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

    path = plan_engine.save_plan(plan)

    assert path.exists()
    assert path.name == 'plan-abcd1234.json'

    loaded = plan_engine.load_plan('abcd1234')

    assert loaded.plan_id == plan.plan_id
    assert loaded.instruction == plan.instruction
    assert len(loaded.operations) == 1
    assert loaded.operations[0].ticket_id == 'T-1'
    assert loaded.status == PlanStatus.SAVED


def test_load_plan_not_found(plan_engine):
    with pytest.raises(FileNotFoundError, match='Plan not found'):
        plan_engine.load_plan('nonexistent')


def test_save_plan_with_parent_plan_id(plan_engine):
    plan = Plan(
        plan_id='child123',
        instruction='re-close bugs',
        operations=[],
        risks=[],
        created_at='2026-01-01T00:00:00Z',
        status=PlanStatus.SAVED,
        parent_plan_id='parent99',
    )

    plan_engine.save_plan(plan)
    loaded = plan_engine.load_plan('child123')

    assert loaded.parent_plan_id == 'parent99'


# --- PLAN_RESPONSE_SCHEMA ---


def test_plan_response_schema_is_valid():
    assert PlanEngine.PLAN_RESPONSE_SCHEMA['type'] == 'object'
    assert 'operations' in PlanEngine.PLAN_RESPONSE_SCHEMA['properties']
    assert 'risks' in PlanEngine.PLAN_RESPONSE_SCHEMA['properties']
    assert set(PlanEngine.PLAN_RESPONSE_SCHEMA['required']) == {'operations', 'risks'}


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
async def test_generate_plan_llm_path(plan_engine):
    ticket = make_ticket(ticket_id='T-1', status='open')
    write_ticket(plan_engine._home, ticket)

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

    with patch('oppie.models.plan_engine.create_llm_provider', return_value=mock_llm):
        plan = await plan_engine.generate('close T-1')

    assert plan.status == PlanStatus.SAVED
    assert len(plan.operations) == 1
    assert plan.operations[0].ticket_id == 'T-1'
    assert plan.operations[0].after_value == 'done'
    assert 'Ticket may not be ready to close' in plan.risks
    assert plan.ticket_snapshots is not None
    assert 'T-1' in plan.ticket_snapshots
    # Verify plan was saved
    loaded = plan_engine.load_plan(plan.plan_id)
    assert loaded.plan_id == plan.plan_id


@pytest.mark.asyncio
async def test_generate_plan_llm_no_structured_output(plan_engine):
    mock_llm = _make_mock_llm(None)
    mock_llm.generate = AsyncMock(
        return_value=LLMResponse(
            text='some text',
            json=None,
            usage=TokenUsage(prompt_tokens=10, completion_tokens=5),
        )
    )

    with (
        patch('oppie.models.plan_engine.create_llm_provider', return_value=mock_llm),
        pytest.raises(ValueError, match='LLM returned no structured output'),
    ):
        await plan_engine.generate('do something')


@pytest.mark.asyncio
async def test_generate_plan_fallback_path(plan_engine):
    ticket = make_ticket(ticket_id='T-1', status='open')
    write_ticket(plan_engine._home, ticket)

    # No config -> LLMNotConfiguredError -> fallback
    plan = await plan_engine.generate('close all tickets')

    assert plan.status == PlanStatus.SAVED
    assert any('without LLM' in r for r in plan.risks)
    assert len(plan.operations) == 1
    assert plan.operations[0].field == 'status'
    assert plan.operations[0].after_value == 'done'
    assert plan.ticket_snapshots is not None
    assert 'T-1' in plan.ticket_snapshots


@pytest.mark.asyncio
async def test_generate_plan_llm_with_preflight_errors(plan_engine):
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

    with patch('oppie.models.plan_engine.create_llm_provider', return_value=mock_llm):
        plan = await plan_engine.generate('close T-MISSING')

    assert plan.status == PlanStatus.INVALID
    assert any('Ticket not found' in r for r in plan.risks)


# --- amend (async) ---


@pytest.mark.asyncio
async def test_amend_links_parent(plan_engine):
    ticket = make_ticket(ticket_id='T-1', status='open')
    write_ticket(plan_engine._home, ticket)

    # Create original plan via fallback
    original = await plan_engine.generate('close all tickets')

    # Amend it (also via fallback since no config)
    amended = await plan_engine.amend(original.plan_id)

    assert amended.parent_plan_id == original.plan_id
    # Amended plan was saved
    loaded = plan_engine.load_plan(amended.plan_id)
    assert loaded.parent_plan_id == original.plan_id


@pytest.mark.asyncio
async def test_amend_not_found(plan_engine):
    with pytest.raises(FileNotFoundError, match='Plan not found'):
        await plan_engine.amend('nonexistent')
