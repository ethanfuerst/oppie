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
