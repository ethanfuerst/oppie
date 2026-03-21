import httpx
import pytest

from oppie.llm._sse import parse_sse_events


def _make_sse_response(*data_lines: str) -> httpx.Response:
    """Build a mock httpx.Response whose aiter_lines() yields SSE-formatted lines."""
    lines = []
    for data in data_lines:
        lines.append(f'data: {data}')
        lines.append('')  # blank line between events

    content = ('\n'.join(lines) + '\n').encode()
    return httpx.Response(200, content=content)


@pytest.mark.asyncio
async def test_parse_sse_events_yields_data_objects():
    resp = _make_sse_response('{"text": "hello"}', '{"text": "world"}')
    events = [e async for e in parse_sse_events(resp)]

    assert len(events) == 2
    assert events[0] == {'text': 'hello'}
    assert events[1] == {'text': 'world'}


@pytest.mark.asyncio
async def test_parse_sse_events_skips_done_sentinel():
    resp = _make_sse_response('{"text": "hi"}', '[DONE]')
    events = [e async for e in parse_sse_events(resp)]

    assert len(events) == 1
    assert events[0] == {'text': 'hi'}


@pytest.mark.asyncio
async def test_parse_sse_events_skips_comments():
    content = b': this is a comment\ndata: {"ok": true}\n\n'
    resp = httpx.Response(200, content=content)
    events = [e async for e in parse_sse_events(resp)]

    assert len(events) == 1
    assert events[0] == {'ok': True}


@pytest.mark.asyncio
async def test_parse_sse_events_skips_empty_lines():
    content = b'\n\ndata: {"a": 1}\n\n\n\n'
    resp = httpx.Response(200, content=content)
    events = [e async for e in parse_sse_events(resp)]

    assert len(events) == 1
    assert events[0] == {'a': 1}
