import httpx
import pytest

from oppie.llm.base import (
    LLMHTTPError,
    LLMNotConfiguredError,
    LLMResponse,
    StreamResult,
    TokenUsage,
    _extract_error_detail,
    _raise_for_llm_status,
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


def test_llm_http_error_exposes_status_and_body():
    exc = LLMHTTPError('400 Bad Request: oops', status_code=400, body='oops')

    assert exc.status_code == 400
    assert exc.body == 'oops'
    assert 'oops' in str(exc)


def test_extract_error_detail_openai_shape():
    resp = httpx.Response(400, json={'error': {'message': 'bad request'}})

    assert _extract_error_detail(resp) == 'bad request'


def test_extract_error_detail_ollama_shape():
    resp = httpx.Response(400, json={'error': 'invalid role "tool_results"'})

    assert _extract_error_detail(resp) == 'invalid role "tool_results"'


def test_extract_error_detail_non_json_falls_back_to_text():
    resp = httpx.Response(500, text='upstream exploded')

    assert _extract_error_detail(resp) == 'upstream exploded'


def test_extract_error_detail_json_without_error_key_falls_back_to_text():
    resp = httpx.Response(400, json={'status': 'error', 'code': 1})

    detail = _extract_error_detail(resp)

    assert '"status"' in detail


def test_extract_error_detail_json_list_falls_back_to_text():
    resp = httpx.Response(400, json=[{'error': 'x'}])

    detail = _extract_error_detail(resp)

    assert 'error' in detail


def test_extract_error_detail_error_dict_missing_message_falls_back_to_text():
    resp = httpx.Response(400, json={'error': {'code': 7}})

    detail = _extract_error_detail(resp)

    assert '"code"' in detail


@pytest.mark.asyncio
async def test_raise_for_llm_status_noop_below_400():
    resp = httpx.Response(200, json={'ok': True})

    await _raise_for_llm_status(resp)


@pytest.mark.asyncio
async def test_raise_for_llm_status_raises_with_openai_detail():
    resp = httpx.Response(
        400,
        json={'error': {'message': 'bad tool_call_id'}},
        request=httpx.Request('POST', 'http://x/chat/completions'),
    )

    with pytest.raises(LLMHTTPError) as excinfo:
        await _raise_for_llm_status(resp)

    assert excinfo.value.status_code == 400
    assert 'bad tool_call_id' in str(excinfo.value)
    assert excinfo.value.body == 'bad tool_call_id'


@pytest.mark.asyncio
async def test_raise_for_llm_status_raises_with_ollama_detail():
    resp = httpx.Response(
        400,
        json={'error': 'invalid role'},
        request=httpx.Request('POST', 'http://x/chat/completions'),
    )

    with pytest.raises(LLMHTTPError) as excinfo:
        await _raise_for_llm_status(resp)

    assert excinfo.value.status_code == 400
    assert excinfo.value.body == 'invalid role'
    assert 'invalid role' in str(excinfo.value)
