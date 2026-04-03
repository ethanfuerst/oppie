import json

import pytest

from oppie.providers.local import LocalProvider
from oppie.tools.base import ToolContext
from oppie.tools.tickets import _execute_get_ticket, _execute_search_tickets
from tests.helpers import make_ticket, setup_instance


@pytest.fixture
def home(tmp_path):
    return setup_instance(tmp_path)


@pytest.fixture
def tool_context(home):
    provider = LocalProvider(home)
    return ToolContext(provider=provider, home=home, capabilities=provider.capabilities)


@pytest.mark.asyncio
async def test_search_tickets_by_status(home, tool_context):
    provider = LocalProvider(home)
    provider.create_ticket(make_ticket(ticket_id='T-1', status='open'))
    provider.create_ticket(make_ticket(ticket_id='T-2', status='done'))
    tool_context.provider = provider

    result = await _execute_search_tickets({'status': 'open'}, tool_context)

    data = json.loads(result.content)
    assert len(data) == 1
    assert data[0]['id'] == 'T-1'


@pytest.mark.asyncio
async def test_search_tickets_all(home, tool_context):
    provider = LocalProvider(home)
    provider.create_ticket(make_ticket(ticket_id='T-1'))
    provider.create_ticket(make_ticket(ticket_id='T-2'))
    tool_context.provider = provider

    result = await _execute_search_tickets({}, tool_context)

    data = json.loads(result.content)
    assert len(data) == 2


@pytest.mark.asyncio
async def test_get_ticket_found(home, tool_context):
    provider = LocalProvider(home)
    provider.create_ticket(make_ticket(ticket_id='T-1'))
    tool_context.provider = provider

    result = await _execute_get_ticket({'ticket_id': 'T-1'}, tool_context)

    assert not result.is_error
    data = json.loads(result.content)
    assert data['id'] == 'T-1'


@pytest.mark.asyncio
async def test_get_ticket_not_found(tool_context):
    result = await _execute_get_ticket({'ticket_id': 'T-MISSING'}, tool_context)

    assert result.is_error
    assert 'not found' in result.content
