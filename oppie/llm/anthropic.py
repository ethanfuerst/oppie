import json
import os
from collections.abc import AsyncIterator
from typing import Any

import httpx

from oppie.llm.base import LLMProvider, LLMResponse, StreamResult, TokenUsage

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
        max_tokens: int = 2000,
        temperature: float = 0.7,
    ) -> LLMResponse:
        system, mapped_messages = _map_messages(messages)
        body: dict[str, Any] = {
            'model': self._model,
            'messages': mapped_messages,
            'max_tokens': max_tokens,
            'temperature': temperature,
        }
        if system:
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
        resp = await self._client.post('/v1/messages', json=body)
        resp.raise_for_status()
        data = resp.json()
        usage = TokenUsage(
            prompt_tokens=data['usage']['input_tokens'],
            completion_tokens=data['usage']['output_tokens'],
        )
        if response_schema is not None:
            tool_block = next(b for b in data['content'] if b['type'] == 'tool_use')
            parsed_json = tool_block['input']
            text = json.dumps(parsed_json)
        else:
            text = ''.join(b['text'] for b in data['content'] if b['type'] == 'text')
            parsed_json = None
        return LLMResponse(text=text, json=parsed_json, usage=usage)

    async def stream(
        self,
        messages: list[dict],
        max_tokens: int = 2000,
        temperature: float = 0.7,
    ) -> StreamResult:
        system, mapped_messages = _map_messages(messages)
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
            return resp.status_code == 200
        except httpx.HTTPError:
            return False


def _map_messages(
    messages: list[dict],
) -> tuple[str | None, list[dict[str, Any]]]:
    """Map OpenAI-style messages to Anthropic format.

    Extract system messages into a single string. Convert remaining
    user/assistant messages to Anthropic's content block format.
    """
    system_parts: list[str] = []
    mapped: list[dict[str, Any]] = []
    for msg in messages:
        role = msg['role']
        content = msg['content']
        if role == 'system':
            system_parts.append(content)
        else:
            mapped.append({'role': role, 'content': content})
    system = '\n\n'.join(system_parts) if system_parts else None
    return system, mapped
