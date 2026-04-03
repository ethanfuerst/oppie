import json

import pytest

from oppie.providers.local import LocalProvider
from oppie.tools.base import ToolContext
from oppie.tools.operations import _execute_propose_operation
from tests.helpers import make_ticket, setup_instance


@pytest.fixture
def home(tmp_path):
    return setup_instance(tmp_path)


@pytest.fixture
def tool_context(home):
    provider = LocalProvider(home)
    return ToolContext(provider=provider, home=home, capabilities=provider.capabilities)


@pytest.mark.asyncio
async def test_propose_valid_operation(home, tool_context):
    provider = LocalProvider(home)
    provider.create_ticket(make_ticket(ticket_id='T-1', status='open'))
    tool_context.provider = provider

    result = await _execute_propose_operation(
        {
            'ticket_id': 'T-1',
            'field': 'status',
            'new_value': 'done',
            'rationale': 'closing it',
        },
        tool_context,
    )

    assert not result.is_error
    data = json.loads(result.content)
    assert data['accepted'] is True
    assert data['before_value'] == 'open'
    assert data['after_value'] == 'done'


@pytest.mark.asyncio
async def test_propose_ticket_not_found(tool_context):
    result = await _execute_propose_operation(
        {
            'ticket_id': 'T-MISSING',
            'field': 'status',
            'new_value': 'done',
            'rationale': 'closing',
        },
        tool_context,
    )

    assert result.is_error
    assert 'not found' in result.content


@pytest.mark.asyncio
async def test_propose_unknown_field(home, tool_context):
    provider = LocalProvider(home)
    provider.create_ticket(make_ticket(ticket_id='T-1'))
    tool_context.provider = provider

    result = await _execute_propose_operation(
        {
            'ticket_id': 'T-1',
            'field': 'nonexistent',
            'new_value': 'x',
            'rationale': 'test',
        },
        tool_context,
    )

    assert result.is_error
    assert 'Unknown field' in result.content


@pytest.mark.asyncio
async def test_propose_invalid_value(home, tool_context):
    provider = LocalProvider(home)
    provider.create_ticket(make_ticket(ticket_id='T-1', status='open'))
    tool_context.provider = provider

    result = await _execute_propose_operation(
        {
            'ticket_id': 'T-1',
            'field': 'status',
            'new_value': 'banana',
            'rationale': 'test',
        },
        tool_context,
    )

    assert result.is_error
    assert 'Invalid value' in result.content
