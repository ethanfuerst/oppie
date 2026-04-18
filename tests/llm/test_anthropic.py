import httpx
import pytest
import respx

from oppie.llm.anthropic import AnthropicProvider, _map_to_anthropic_format


def test_map_to_anthropic_format_extracts_system():
    messages = [
        {'role': 'system', 'content': 'You are helpful.'},
        {'role': 'user', 'content': 'Hi'},
    ]
    system, mapped = _map_to_anthropic_format(messages)

    assert system == 'You are helpful.'
    assert len(mapped) == 1
    assert mapped[0] == {'role': 'user', 'content': 'Hi'}


def test_map_to_anthropic_format_no_system():
    messages = [{'role': 'user', 'content': 'Hi'}]
    system, mapped = _map_to_anthropic_format(messages)

    assert system is None
    assert len(mapped) == 1


def test_map_to_anthropic_format_multiple_system():
    messages = [
        {'role': 'system', 'content': 'First.'},
        {'role': 'system', 'content': 'Second.'},
        {'role': 'user', 'content': 'Hi'},
    ]
    system, mapped = _map_to_anthropic_format(messages)

    assert system == 'First.\n\nSecond.'
    assert len(mapped) == 1


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-key')
    return AnthropicProvider(model='claude-test')


@pytest.mark.asyncio
async def test_generate_returns_llm_response(provider):
    with respx.mock:
        respx.post('https://api.anthropic.com/v1/messages').mock(
            return_value=httpx.Response(
                200,
                json={
                    'content': [{'type': 'text', 'text': 'Hello!'}],
                    'usage': {'input_tokens': 10, 'output_tokens': 5},
                },
            )
        )
        result = await provider.generate(messages=[{'role': 'user', 'content': 'Hi'}])

    assert result.text == 'Hello!'
    assert result.usage.prompt_tokens == 10
    assert result.usage.completion_tokens == 5
    assert result.json is None


@pytest.mark.asyncio
async def test_generate_with_structured_output(provider):
    with respx.mock:
        respx.post('https://api.anthropic.com/v1/messages').mock(
            return_value=httpx.Response(
                200,
                json={
                    'content': [
                        {
                            'type': 'tool_use',
                            'id': 'tu_1',
                            'name': 'structured_response',
                            'input': {'answer': 42},
                        }
                    ],
                    'usage': {'input_tokens': 10, 'output_tokens': 5},
                },
            )
        )
        result = await provider.generate(
            messages=[{'role': 'user', 'content': 'answer?'}],
            response_schema={
                'type': 'object',
                'properties': {'answer': {'type': 'integer'}},
            },
        )

    assert result.json == {'answer': 42}
    assert result.text == '{"answer": 42}'


@pytest.mark.asyncio
async def test_generate_maps_tool_schema_to_input_schema(provider):
    captured_body = {}

    def capture_request(request):
        import json as _json

        captured_body.update(_json.loads(request.content))
        return httpx.Response(
            200,
            json={
                'content': [{'type': 'text', 'text': 'ok'}],
                'usage': {'input_tokens': 1, 'output_tokens': 1},
            },
        )

    tool_schema = {'type': 'object', 'properties': {'q': {'type': 'string'}}}
    with respx.mock:
        respx.post('https://api.anthropic.com/v1/messages').mock(
            side_effect=capture_request
        )
        await provider.generate(
            messages=[{'role': 'user', 'content': 'hi'}],
            tools=[
                {
                    'name': 'search',
                    'description': 'Search tickets.',
                    'schema': tool_schema,
                }
            ],
        )

    assert captured_body['tools'][0]['name'] == 'search'
    assert captured_body['tools'][0]['description'] == 'Search tickets.'
    assert captured_body['tools'][0]['input_schema'] == tool_schema


@pytest.mark.asyncio
async def test_generate_with_system_message(provider):
    with respx.mock:
        respx.post('https://api.anthropic.com/v1/messages').mock(
            return_value=httpx.Response(
                200,
                json={
                    'content': [{'type': 'text', 'text': 'Hi!'}],
                    'usage': {'input_tokens': 15, 'output_tokens': 3},
                },
            )
        )
        result = await provider.generate(
            messages=[
                {'role': 'system', 'content': 'Be concise.'},
                {'role': 'user', 'content': 'Hi'},
            ]
        )

    assert result.text == 'Hi!'


@pytest.mark.asyncio
async def test_test_connection_success(provider):
    with respx.mock:
        respx.post('https://api.anthropic.com/v1/messages').mock(
            return_value=httpx.Response(
                200,
                json={
                    'content': [{'type': 'text', 'text': 'pong'}],
                    'usage': {'input_tokens': 1, 'output_tokens': 1},
                },
            )
        )
        result = await provider.test_connection()

    assert result is True


@pytest.mark.asyncio
async def test_test_connection_failure(provider):
    with respx.mock:
        respx.post('https://api.anthropic.com/v1/messages').mock(
            side_effect=httpx.ConnectError('refused')
        )
        result = await provider.test_connection()

    assert result is False


@pytest.mark.asyncio
async def test_close_closes_client(provider):
    await provider.close()

    assert provider._client.is_closed


@pytest.mark.asyncio
async def test_async_context_manager(provider):
    async with provider as p:
        assert p is provider

    assert provider._client.is_closed


@pytest.mark.asyncio
async def test_generate_with_system_parts_sends_structured_blocks(provider):
    """When system_parts is provided, Anthropic body uses structured system blocks."""
    captured_body = {}

    def capture_request(request):
        import json as _json

        captured_body.update(_json.loads(request.content))
        return httpx.Response(
            200,
            json={
                'content': [{'type': 'text', 'text': 'ok'}],
                'usage': {'input_tokens': 10, 'output_tokens': 5},
            },
        )

    with respx.mock:
        respx.post('https://api.anthropic.com/v1/messages').mock(
            side_effect=capture_request
        )
        await provider.generate(
            messages=[
                {'role': 'system', 'content': 'flat system'},
                {'role': 'user', 'content': 'Hi'},
            ],
            system_parts=[
                {'content': 'Base prompt.', 'cache_control': {'type': 'ephemeral'}},
                {'content': 'Context docs.', 'cache_control': {'type': 'ephemeral'}},
                {'content': 'Dynamic info.'},
            ],
        )

    assert isinstance(captured_body['system'], list)
    assert len(captured_body['system']) == 3
    assert captured_body['system'][0] == {
        'type': 'text',
        'text': 'Base prompt.',
        'cache_control': {'type': 'ephemeral'},
    }
    assert captured_body['system'][1] == {
        'type': 'text',
        'text': 'Context docs.',
        'cache_control': {'type': 'ephemeral'},
    }
    assert captured_body['system'][2] == {
        'type': 'text',
        'text': 'Dynamic info.',
    }


@pytest.mark.asyncio
async def test_generate_without_system_parts_uses_flat_string(provider):
    """When system_parts is None, fall back to flat system string from messages."""
    captured_body = {}

    def capture_request(request):
        import json as _json

        captured_body.update(_json.loads(request.content))
        return httpx.Response(
            200,
            json={
                'content': [{'type': 'text', 'text': 'ok'}],
                'usage': {'input_tokens': 10, 'output_tokens': 5},
            },
        )

    with respx.mock:
        respx.post('https://api.anthropic.com/v1/messages').mock(
            side_effect=capture_request
        )
        await provider.generate(
            messages=[
                {'role': 'system', 'content': 'Be helpful.'},
                {'role': 'user', 'content': 'Hi'},
            ],
        )

    assert captured_body['system'] == 'Be helpful.'
