import httpx
import pytest
import respx

from oppie.llm.openai_compatible import OpenAICompatibleProvider


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
