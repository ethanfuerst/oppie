import json

import httpx
import pytest
import respx

from oppie.llm.base import LLMHTTPError
from oppie.llm.openai_compatible import OpenAICompatibleProvider, _map_to_openai_format


@pytest.fixture
def provider():
    return OpenAICompatibleProvider(
        model='test-model',
        endpoint='http://test-server/v1',
    )


def test_api_key_sets_auth_header(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test-123')
    p = OpenAICompatibleProvider(model='m', endpoint='http://localhost/v1')

    assert p._client.headers['authorization'] == 'Bearer sk-test-123'


@pytest.mark.asyncio
async def test_generate_returns_llm_response(provider):
    with respx.mock:
        respx.post('http://test-server/v1/chat/completions').mock(
            return_value=httpx.Response(
                200,
                json={
                    'choices': [{'message': {'content': 'Hello!'}}],
                    'usage': {'prompt_tokens': 10, 'completion_tokens': 5},
                },
            )
        )
        result = await provider.generate(messages=[{'role': 'user', 'content': 'Hi'}])

    assert result.text == 'Hello!'
    assert result.usage.prompt_tokens == 10
    assert result.usage.completion_tokens == 5
    assert result.json is None


@pytest.mark.asyncio
async def test_generate_with_response_schema(provider):
    with respx.mock:
        respx.post('http://test-server/v1/chat/completions').mock(
            return_value=httpx.Response(
                200,
                json={
                    'choices': [{'message': {'content': '{"answer": 42}'}}],
                    'usage': {'prompt_tokens': 10, 'completion_tokens': 5},
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
async def test_generate_maps_tool_schema_to_parameters(provider):
    captured_body = {}

    def capture_request(request):
        import json as _json

        captured_body.update(_json.loads(request.content))
        return httpx.Response(
            200,
            json={
                'choices': [{'message': {'content': 'ok'}}],
                'usage': {'prompt_tokens': 1, 'completion_tokens': 1},
            },
        )

    tool_schema = {'type': 'object', 'properties': {'q': {'type': 'string'}}}
    with respx.mock:
        respx.post('http://test-server/v1/chat/completions').mock(
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

    assert captured_body['tools'][0]['type'] == 'function'
    assert captured_body['tools'][0]['function']['name'] == 'search'
    assert captured_body['tools'][0]['function']['description'] == 'Search tickets.'
    assert captured_body['tools'][0]['function']['parameters'] == tool_schema


@pytest.mark.asyncio
async def test_test_connection_success(provider):
    with respx.mock:
        respx.get('http://test-server/v1/models').mock(
            return_value=httpx.Response(200, json={'data': []})
        )
        result = await provider.test_connection()

    assert result is True


@pytest.mark.asyncio
async def test_test_connection_failure(provider):
    with respx.mock:
        respx.get('http://test-server/v1/models').mock(
            side_effect=httpx.ConnectError('refused')
        )
        result = await provider.test_connection()

    assert result is False


@pytest.mark.asyncio
async def test_close_closes_client(provider):
    with respx.mock:
        await provider.close()

    assert provider._client.is_closed


@pytest.mark.asyncio
async def test_async_context_manager(provider):
    with respx.mock:
        async with provider as p:
            assert p is provider

    assert provider._client.is_closed


@pytest.mark.asyncio
async def test_generate_raises_llm_http_error_with_openai_body(provider):
    with respx.mock:
        respx.post('http://test-server/v1/chat/completions').mock(
            return_value=httpx.Response(
                400,
                json={'error': {'message': 'bad tool_call_id'}},
            )
        )
        with pytest.raises(LLMHTTPError) as excinfo:
            await provider.generate(messages=[{'role': 'user', 'content': 'hi'}])

    assert excinfo.value.status_code == 400
    assert 'bad tool_call_id' in str(excinfo.value)
    assert excinfo.value.body == 'bad tool_call_id'


def test_map_to_openai_format_passthrough_for_plain_messages():
    messages = [
        {'role': 'system', 'content': 'be brief'},
        {'role': 'user', 'content': 'hi'},
    ]

    assert _map_to_openai_format(messages) == messages


def test_map_to_openai_format_assistant_tool_calls_become_spec_shape():
    messages = [
        {
            'role': 'assistant',
            'content': '',
            'tool_calls': [
                {'id': 'call_1', 'name': 'search', 'input': {'q': 'open'}},
            ],
        }
    ]
    out = _map_to_openai_format(messages)

    assert out[0]['role'] == 'assistant'
    assert out[0]['content'] is None
    assert out[0]['tool_calls'][0]['id'] == 'call_1'
    assert out[0]['tool_calls'][0]['type'] == 'function'
    assert out[0]['tool_calls'][0]['function']['name'] == 'search'
    arguments = out[0]['tool_calls'][0]['function']['arguments']

    assert isinstance(arguments, str)
    assert json.loads(arguments) == {'q': 'open'}


def test_map_to_openai_format_preserves_non_empty_assistant_content():
    messages = [
        {
            'role': 'assistant',
            'content': 'thinking out loud',
            'tool_calls': [
                {'id': 'call_1', 'name': 'search', 'input': {}},
            ],
        }
    ]
    out = _map_to_openai_format(messages)

    assert out[0]['content'] == 'thinking out loud'


def test_map_to_openai_format_tool_results_fan_out_and_flag_error():
    messages = [
        {
            'role': 'tool_results',
            'results': [
                {'tool_call_id': 'call_1', 'content': '[]', 'is_error': False},
                {'tool_call_id': 'call_2', 'content': 'boom', 'is_error': True},
            ],
        }
    ]
    out = _map_to_openai_format(messages)

    assert len(out) == 2
    assert out[0] == {'role': 'tool', 'tool_call_id': 'call_1', 'content': '[]'}
    assert out[1] == {
        'role': 'tool',
        'tool_call_id': 'call_2',
        'content': 'Error: boom',
    }


@pytest.mark.asyncio
async def test_generate_second_turn_sends_spec_conformant_payload(provider):
    """Regression for ETH-414: second round-trip after tool calls must not 400."""
    captured_bodies = []

    def capture(request):
        captured_bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                'choices': [{'message': {'content': 'final answer'}}],
                'usage': {'prompt_tokens': 5, 'completion_tokens': 3},
            },
        )

    with respx.mock:
        respx.post('http://test-server/v1/chat/completions').mock(side_effect=capture)
        second_turn_messages = [
            {'role': 'system', 'content': 'sys'},
            {'role': 'user', 'content': 'what is open?'},
            {
                'role': 'assistant',
                'content': '',
                'tool_calls': [
                    {
                        'id': 'call_1',
                        'name': 'search_tickets',
                        'input': {'status': 'open'},
                    },
                ],
            },
            {
                'role': 'tool_results',
                'results': [
                    {'tool_call_id': 'call_1', 'content': '[]', 'is_error': False},
                ],
            },
        ]
        await provider.generate(messages=second_turn_messages)

    sent = captured_bodies[0]['messages']
    assistant = next(m for m in sent if m['role'] == 'assistant')

    assert assistant['content'] is None
    assert assistant['tool_calls'][0]['type'] == 'function'
    assert assistant['tool_calls'][0]['function']['name'] == 'search_tickets'
    assert isinstance(assistant['tool_calls'][0]['function']['arguments'], str)
    assert json.loads(assistant['tool_calls'][0]['function']['arguments']) == {
        'status': 'open'
    }
    tool_msgs = [m for m in sent if m['role'] == 'tool']

    assert len(tool_msgs) == 1
    assert tool_msgs[0]['tool_call_id'] == 'call_1'
    assert tool_msgs[0]['content'] == '[]'
    assert not any(m.get('role') == 'tool_results' for m in sent)


@pytest.mark.asyncio
async def test_generate_raises_llm_http_error_with_ollama_body(provider):
    with respx.mock:
        respx.post('http://test-server/v1/chat/completions').mock(
            return_value=httpx.Response(
                400,
                json={'error': 'invalid role "tool_results"'},
            )
        )
        with pytest.raises(LLMHTTPError) as excinfo:
            await provider.generate(messages=[{'role': 'user', 'content': 'hi'}])

    assert excinfo.value.status_code == 400
    assert 'invalid role' in excinfo.value.body
