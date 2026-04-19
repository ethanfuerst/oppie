import httpx
import pytest
import respx

from oppie.llm.anthropic import AnthropicProvider
from oppie.llm.base import LLMHTTPError


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-key')
    return AnthropicProvider(model='claude-test')


@pytest.mark.asyncio
async def test_stream_yields_text_chunks(provider):
    sse_body = (
        'event: message_start\n'
        'data: {"type": "message_start", "message": {"usage": {"input_tokens": 10}}}\n\n'
        'event: content_block_delta\n'
        'data: {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hello"}}\n\n'
        'event: content_block_delta\n'
        'data: {"type": "content_block_delta", "delta": {"type": "text_delta", "text": " world"}}\n\n'
        'event: message_delta\n'
        'data: {"type": "message_delta", "usage": {"output_tokens": 5}}\n\n'
    )
    with respx.mock:
        respx.post('https://api.anthropic.com/v1/messages').mock(
            return_value=httpx.Response(
                200,
                content=sse_body.encode(),
                headers={'content-type': 'text/event-stream'},
            )
        )
        result = await provider.stream(messages=[{'role': 'user', 'content': 'Hi'}])
        chunks = [chunk async for chunk in result]

    assert chunks == ['Hello', ' world']
    assert result.usage is not None
    assert result.usage.prompt_tokens == 10
    assert result.usage.completion_tokens == 5


@pytest.mark.asyncio
async def test_stream_with_system_message(provider):
    sse_body = (
        'event: message_start\n'
        'data: {"type": "message_start", "message": {"usage": {"input_tokens": 5}}}\n\n'
        'event: content_block_delta\n'
        'data: {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "ok"}}\n\n'
        'event: message_delta\n'
        'data: {"type": "message_delta", "usage": {"output_tokens": 1}}\n\n'
    )
    with respx.mock:
        respx.post('https://api.anthropic.com/v1/messages').mock(
            return_value=httpx.Response(
                200,
                content=sse_body.encode(),
                headers={'content-type': 'text/event-stream'},
            )
        )
        result = await provider.stream(
            messages=[
                {'role': 'system', 'content': 'Be brief.'},
                {'role': 'user', 'content': 'Hi'},
            ]
        )
        chunks = [chunk async for chunk in result]

    assert chunks == ['ok']


@pytest.mark.asyncio
async def test_stream_raises_llm_http_error_with_body(provider):
    with respx.mock:
        respx.post('https://api.anthropic.com/v1/messages').mock(
            return_value=httpx.Response(
                429,
                json={'error': {'type': 'rate_limit', 'message': 'too fast'}},
            )
        )
        result = await provider.stream(messages=[{'role': 'user', 'content': 'hi'}])
        with pytest.raises(LLMHTTPError) as excinfo:
            async for _ in result:
                pass

    assert excinfo.value.status_code == 429
    assert 'too fast' in str(excinfo.value)
