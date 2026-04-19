from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from oppie.llm._sse import parse_sse_events
from oppie.llm.base import (
    LLMProvider,
    LLMResponse,
    StreamResult,
    TokenUsage,
    ToolCallRequest,
    _raise_for_llm_status,
)

logger = logging.getLogger(__name__)


def _map_to_openai_format(messages: list[dict]) -> list[dict]:
    """Map the engine's neutral message format to OpenAI chat-completions wire format.

    - {role: 'assistant', content, tool_calls: [{id, name, input}]}
        -> {role: 'assistant', content, tool_calls: [{id, type: 'function',
            function: {name, arguments: <JSON string>}}]}
    - {role: 'tool_results', results: [{tool_call_id, content, is_error}, ...]}
        -> one {role: 'tool', tool_call_id, content} message per result
          (is_error=True prefixes content with 'Error: ').
    - other messages pass through unchanged.
    """
    mapped: list[dict] = []
    for msg in messages:
        role = msg.get('role')
        if role == 'tool_results':
            for r in msg['results']:
                content = r['content']
                if r.get('is_error'):
                    content = f'Error: {content}'
                mapped.append(
                    {
                        'role': 'tool',
                        'tool_call_id': r['tool_call_id'],
                        'content': content,
                    }
                )
        elif role == 'assistant' and 'tool_calls' in msg:
            mapped.append(
                {
                    'role': 'assistant',
                    'content': msg.get('content') or None,
                    'tool_calls': [
                        {
                            'id': tc['id'],
                            'type': 'function',
                            'function': {
                                'name': tc['name'],
                                'arguments': json.dumps(tc['input']),
                            },
                        }
                        for tc in msg['tool_calls']
                    ],
                }
            )
        else:
            mapped.append(msg)
    return mapped


class OpenAICompatibleProvider(LLMProvider):
    """LLM provider for OpenAI-compatible APIs (Ollama, llama.cpp, OpenAI)."""

    def __init__(
        self,
        model: str,
        endpoint: str = 'http://localhost:8080/v1',
        timeout: float = 120.0,
    ) -> None:
        if httpx is None:
            raise ImportError(
                "OpenAI-compatible LLM backend requires the 'openai' extra.\n"
                "Install with: pip install 'oppie[openai]'"
            )
        self._model = model
        self._endpoint = endpoint.rstrip('/')
        self._timeout = timeout
        api_key = os.environ.get('OPENAI_API_KEY', '')
        headers: dict[str, str] = {}
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'
        self._client = httpx.AsyncClient(
            base_url=self._endpoint,
            headers=headers,
            timeout=timeout,
        )

    async def generate(
        self,
        messages: list[dict],
        response_schema: dict | None = None,
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        system_parts: list[dict] | None = None,
    ) -> LLMResponse:
        logger.debug(
            'OpenAI generate: model=%s max_tokens=%d temp=%.1f',
            self._model,
            max_tokens,
            temperature,
        )
        body: dict = {
            'model': self._model,
            'messages': _map_to_openai_format(messages),
            'max_tokens': max_tokens,
            'temperature': temperature,
        }
        if response_schema is not None:
            body['response_format'] = {
                'type': 'json_schema',
                'json_schema': {'name': 'response', 'schema': response_schema},
            }
        elif tools is not None:
            body['tools'] = [
                {
                    'type': 'function',
                    'function': {
                        'name': t['name'],
                        'description': t.get('description', ''),
                        'parameters': t['schema'],
                    },
                }
                for t in tools
            ]
            if tool_choice is not None:
                if tool_choice == 'any':
                    body['tool_choice'] = 'required'
                elif isinstance(tool_choice, dict) and 'name' in tool_choice:
                    body['tool_choice'] = {
                        'type': 'function',
                        'function': {'name': tool_choice['name']},
                    }
        resp = await self._client.post('/chat/completions', json=body)
        await _raise_for_llm_status(resp)
        data = resp.json()
        message = data['choices'][0]['message']
        text = message.get('content') or ''
        usage = TokenUsage(
            prompt_tokens=data['usage']['prompt_tokens'],
            completion_tokens=data['usage']['completion_tokens'],
        )
        logger.debug(
            'OpenAI response: prompt_tokens=%d completion_tokens=%d',
            usage.prompt_tokens,
            usage.completion_tokens,
        )
        parsed_json = None
        if response_schema is not None:
            parsed_json = json.loads(text)
        tool_calls: list[ToolCallRequest] = []
        raw_tool_calls = message.get('tool_calls')
        if raw_tool_calls:
            for tc in raw_tool_calls:
                tool_calls.append(
                    ToolCallRequest(
                        id=tc['id'],
                        name=tc['function']['name'],
                        input=json.loads(tc['function']['arguments']),
                    )
                )
        stop_reason = 'tool_use' if tool_calls else 'end_turn'
        return LLMResponse(
            text=text,
            json=parsed_json,
            usage=usage,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
        )

    async def stream(
        self,
        messages: list[dict],
        max_tokens: int = 2000,
        temperature: float = 0.7,
    ) -> StreamResult:
        body = {
            'model': self._model,
            'messages': _map_to_openai_format(messages),
            'max_tokens': max_tokens,
            'temperature': temperature,
            'stream': True,
            'stream_options': {'include_usage': True},
        }
        result = StreamResult.__new__(StreamResult)
        result.usage = None
        result._iterator = self._stream_chunks(body, result)
        return result

    async def _stream_chunks(
        self, body: dict, result: StreamResult
    ) -> AsyncIterator[str]:
        logger.debug('OpenAI stream started: model=%s', self._model)
        usage: TokenUsage | None = None
        async with self._client.stream('POST', '/chat/completions', json=body) as resp:
            await _raise_for_llm_status(resp)
            async for event in parse_sse_events(resp):
                choices = event.get('choices', [])
                if choices:
                    delta = choices[0].get('delta', {})
                    content = delta.get('content')
                    if content:
                        yield content
                if 'usage' in event and event['usage']:
                    usage = TokenUsage(
                        prompt_tokens=event['usage']['prompt_tokens'],
                        completion_tokens=event['usage']['completion_tokens'],
                    )
        if usage:
            logger.debug(
                'OpenAI stream complete: prompt_tokens=%d completion_tokens=%d',
                usage.prompt_tokens,
                usage.completion_tokens,
            )
        result.usage = usage

    async def close(self) -> None:
        await self._client.aclose()

    async def test_connection(self) -> bool:
        try:
            resp = await self._client.get('/models')
            result = resp.status_code == 200
        except httpx.HTTPError:
            result = False
        logger.debug('OpenAI connection test: %s', 'ok' if result else 'failed')
        return result
