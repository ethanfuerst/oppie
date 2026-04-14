from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING, Any

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from oppie.llm.base import (
    LLMProvider,
    LLMResponse,
    StreamResult,
    TokenUsage,
    ToolCallRequest,
)

logger = logging.getLogger(__name__)

_ANTHROPIC_API_URL = 'https://api.anthropic.com'
_ANTHROPIC_VERSION = '2023-06-01'


class AnthropicProvider(LLMProvider):
    """LLM provider for the Anthropic (Claude) API."""

    def __init__(
        self,
        model: str,
        endpoint: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        if httpx is None:
            raise ImportError(
                "LLM backend requires the 'llm' extra. "
                "Install with: pip install 'oppie[llm]'"
            )
        self._model = model
        api_key = os.environ.get('ANTHROPIC_API_KEY', '')
        base_url = endpoint or _ANTHROPIC_API_URL
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip('/'),
            headers={
                'x-api-key': api_key,
                'anthropic-version': _ANTHROPIC_VERSION,
                'content-type': 'application/json',
            },
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
            'Anthropic generate: model=%s max_tokens=%d temp=%.1f',
            self._model,
            max_tokens,
            temperature,
        )
        system, mapped_messages = _map_to_anthropic_format(messages)
        body: dict[str, Any] = {
            'model': self._model,
            'messages': mapped_messages,
            'max_tokens': max_tokens,
            'temperature': temperature,
        }
        if system_parts:
            body['system'] = [
                {
                    'type': 'text',
                    'text': part['content'],
                    **(
                        {'cache_control': part['cache_control']}
                        if part.get('cache_control')
                        else {}
                    ),
                }
                for part in system_parts
            ]
        elif system:
            body['system'] = system
        if response_schema is not None:
            body['tools'] = [
                {
                    'name': 'structured_response',
                    'description': 'Return structured output matching the schema.',
                    'input_schema': response_schema,
                }
            ]
            body['tool_choice'] = {'type': 'tool', 'name': 'structured_response'}
        elif tools is not None:
            body['tools'] = [
                {
                    'name': t['name'],
                    'description': t.get('description', ''),
                    'input_schema': t['parameters'],
                }
                for t in tools
            ]
            if tool_choice is not None:
                if tool_choice == 'any':
                    body['tool_choice'] = {'type': 'any'}
                elif isinstance(tool_choice, dict) and 'name' in tool_choice:
                    body['tool_choice'] = {
                        'type': 'tool',
                        'name': tool_choice['name'],
                    }
        resp = await self._client.post('/v1/messages', json=body)
        resp.raise_for_status()
        data = resp.json()
        usage = TokenUsage(
            prompt_tokens=data['usage']['input_tokens'],
            completion_tokens=data['usage']['output_tokens'],
        )
        logger.debug(
            'Anthropic response: prompt_tokens=%d completion_tokens=%d',
            usage.prompt_tokens,
            usage.completion_tokens,
        )
        stop_reason = data.get('stop_reason', 'end_turn')
        if response_schema is not None:
            tool_block = next(b for b in data['content'] if b['type'] == 'tool_use')
            parsed_json = tool_block['input']
            text = json.dumps(parsed_json)
            return LLMResponse(text=text, json=parsed_json, usage=usage)
        text_parts: list[str] = []
        tool_calls: list[ToolCallRequest] = []
        for block in data['content']:
            if block['type'] == 'text':
                text_parts.append(block['text'])
            elif block['type'] == 'tool_use':
                tool_calls.append(
                    ToolCallRequest(
                        id=block['id'],
                        name=block['name'],
                        input=block['input'],
                    )
                )
        text = ''.join(text_parts)
        parsed_json = None
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
        system, mapped_messages = _map_to_anthropic_format(messages)
        body: dict[str, Any] = {
            'model': self._model,
            'messages': mapped_messages,
            'max_tokens': max_tokens,
            'temperature': temperature,
            'stream': True,
        }
        if system:
            body['system'] = system
        result = StreamResult.__new__(StreamResult)
        result.usage = None
        result._iterator = self._stream_chunks(body, result)
        return result

    async def _stream_chunks(
        self, body: dict, result: StreamResult
    ) -> AsyncIterator[str]:
        logger.debug('Anthropic stream started: model=%s', self._model)
        prompt_tokens = 0
        completion_tokens = 0
        async with self._client.stream('POST', '/v1/messages', json=body) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or line.startswith(':'):
                    continue
                if line.startswith('event: '):
                    continue
                if line.startswith('data: '):
                    data = json.loads(line[6:])
                    if data.get('type') == 'content_block_delta':
                        delta = data.get('delta', {})
                        if delta.get('type') == 'text_delta':
                            yield delta['text']
                    elif data.get('type') == 'message_start':
                        u = data.get('message', {}).get('usage', {})
                        prompt_tokens = u.get('input_tokens', 0)
                    elif data.get('type') == 'message_delta':
                        u = data.get('usage', {})
                        completion_tokens = u.get('output_tokens', 0)
        result.usage = TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        logger.debug(
            'Anthropic stream complete: prompt_tokens=%d completion_tokens=%d',
            prompt_tokens,
            completion_tokens,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def test_connection(self) -> bool:
        try:
            resp = await self._client.post(
                '/v1/messages',
                json={
                    'model': self._model,
                    'messages': [{'role': 'user', 'content': 'ping'}],
                    'max_tokens': 1,
                },
            )
            result = resp.status_code == 200
        except httpx.HTTPError:
            result = False
        logger.debug('Anthropic connection test: %s', 'ok' if result else 'failed')
        return result


def _map_to_anthropic_format(
    messages: list[dict],
) -> tuple[str | None, list[dict[str, Any]]]:
    """Map OpenAI-style messages to Anthropic format.

    Extract system messages. Convert user/assistant/tool messages.
    """
    system_parts: list[str] = []
    mapped: list[dict[str, Any]] = []
    for msg in messages:
        role = msg['role']
        content = msg['content']
        if role == 'system':
            system_parts.append(content)
        elif role == 'tool_results':
            mapped.append(
                {
                    'role': 'user',
                    'content': [
                        {
                            'type': 'tool_result',
                            'tool_use_id': r['tool_call_id'],
                            'content': r['content'],
                            'is_error': r.get('is_error', False),
                        }
                        for r in msg['results']
                    ],
                }
            )
        elif role == 'assistant' and 'tool_calls' in msg:
            blocks: list[dict] = []
            if content:
                blocks.append({'type': 'text', 'text': content})
            for tc in msg['tool_calls']:
                blocks.append(
                    {
                        'type': 'tool_use',
                        'id': tc['id'],
                        'name': tc['name'],
                        'input': tc['input'],
                    }
                )
            mapped.append({'role': 'assistant', 'content': blocks})
        else:
            mapped.append({'role': role, 'content': content})
    system = '\n\n'.join(system_parts) if system_parts else None
    return system, mapped
