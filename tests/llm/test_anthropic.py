import httpx
import pytest
import respx

from oppie.llm.anthropic import AnthropicProvider, _map_messages


def test_map_messages_extracts_system():
    messages = [
        {'role': 'system', 'content': 'You are helpful.'},
        {'role': 'user', 'content': 'Hi'},
    ]
    system, mapped = _map_messages(messages)

    assert system == 'You are helpful.'
    assert len(mapped) == 1
    assert mapped[0] == {'role': 'user', 'content': 'Hi'}


def test_map_messages_no_system():
    messages = [{'role': 'user', 'content': 'Hi'}]
    system, mapped = _map_messages(messages)

    assert system is None
    assert len(mapped) == 1


def test_map_messages_multiple_system():
    messages = [
        {'role': 'system', 'content': 'First.'},
        {'role': 'system', 'content': 'Second.'},
        {'role': 'user', 'content': 'Hi'},
    ]
    system, mapped = _map_messages(messages)

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
