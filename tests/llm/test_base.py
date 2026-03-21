import pytest

from oppie.llm.base import (
    LLMNotConfiguredError,
    LLMResponse,
    StreamResult,
    TokenUsage,
)


def test_token_usage_to_dict():
    usage = TokenUsage(prompt_tokens=10, completion_tokens=20)

    assert usage.to_dict() == {'prompt_tokens': 10, 'completion_tokens': 20}


def test_token_usage_from_dict():
    data = {'prompt_tokens': 5, 'completion_tokens': 15}
    usage = TokenUsage.from_dict(data)

    assert usage.prompt_tokens == 5
    assert usage.completion_tokens == 15


def test_llm_response_to_dict_and_from_dict():
    resp = LLMResponse(
        text='hello',
        json={'key': 'value'},
        usage=TokenUsage(prompt_tokens=1, completion_tokens=2),
    )
    data = resp.to_dict()
    restored = LLMResponse.from_dict(data)

    assert restored.text == 'hello'
    assert restored.json == {'key': 'value'}
    assert restored.usage.prompt_tokens == 1
    assert restored.usage.completion_tokens == 2


def test_llm_response_from_dict_without_json():
    data = {
        'text': 'hello',
        'usage': {'prompt_tokens': 1, 'completion_tokens': 2},
    }
    restored = LLMResponse.from_dict(data)

    assert restored.json is None


def test_llm_not_configured_error():
    with pytest.raises(LLMNotConfiguredError):
        raise LLMNotConfiguredError('no config')


@pytest.mark.asyncio
async def test_stream_result_iterates_and_exposes_usage():
    async def fake_gen(result: StreamResult):
        yield 'hello '
        yield 'world'
        result.usage = TokenUsage(prompt_tokens=5, completion_tokens=10)

    result = StreamResult.__new__(StreamResult)
    result.usage = None
    result._iterator = fake_gen(result)

    chunks = [chunk async for chunk in result]

    assert chunks == ['hello ', 'world']
    assert result.usage is not None
    assert result.usage.completion_tokens == 10


@pytest.mark.asyncio
async def test_stream_result_usage_is_none_before_iteration():
    async def fake_gen():
        yield 'chunk'

    result = StreamResult(fake_gen())

    assert result.usage is None
