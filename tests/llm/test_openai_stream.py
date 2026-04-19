import httpx
import pytest
import respx

from oppie.llm.base import LLMHTTPError
from oppie.llm.openai_compatible import OpenAICompatibleProvider


@pytest.fixture
def provider():
    return OpenAICompatibleProvider(
        model='test-model',
        endpoint='http://test-server/v1',
    )


@pytest.mark.asyncio
async def test_stream_yields_text_chunks(provider):
    sse_body = (
        'data: {"choices": [{"delta": {"content": "Hello"}}]}\n\n'
        'data: {"choices": [{"delta": {"content": " world"}}]}\n\n'
        'data: {"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 5}}\n\n'
        'data: [DONE]\n\n'
    )
    with respx.mock:
        respx.post('http://test-server/v1/chat/completions').mock(
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
async def test_stream_raises_llm_http_error_with_body(provider):
    with respx.mock:
        respx.post('http://test-server/v1/chat/completions').mock(
            return_value=httpx.Response(
                400,
                json={'error': {'message': 'bad stream'}},
            )
        )
        result = await provider.stream(messages=[{'role': 'user', 'content': 'hi'}])
        with pytest.raises(LLMHTTPError) as excinfo:
            async for _ in result:
                pass

    assert excinfo.value.status_code == 400
    assert 'bad stream' in str(excinfo.value)
