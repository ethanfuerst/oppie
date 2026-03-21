import json
import os
from collections.abc import AsyncIterator

import httpx

from oppie.llm._sse import parse_sse_events
from oppie.llm.base import LLMProvider, LLMResponse, StreamResult, TokenUsage


class OpenAICompatibleProvider(LLMProvider):
    """LLM provider for OpenAI-compatible APIs (Ollama, llama.cpp, OpenAI)."""

    def __init__(
        self,
        model: str,
        endpoint: str = 'http://localhost:8080/v1',
        timeout: float = 120.0,
    ) -> None:
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
        max_tokens: int = 2000,
        temperature: float = 0.7,
    ) -> LLMResponse:
        body: dict = {
            'model': self._model,
            'messages': messages,
            'max_tokens': max_tokens,
            'temperature': temperature,
        }
        if response_schema is not None:
            body['response_format'] = {
                'type': 'json_schema',
                'json_schema': {'name': 'response', 'schema': response_schema},
            }
        resp = await self._client.post('/chat/completions', json=body)
        resp.raise_for_status()
        data = resp.json()
        text = data['choices'][0]['message']['content']
        usage = TokenUsage(
            prompt_tokens=data['usage']['prompt_tokens'],
            completion_tokens=data['usage']['completion_tokens'],
        )
        parsed_json = None
        if response_schema is not None:
            parsed_json = json.loads(text)
        return LLMResponse(text=text, json=parsed_json, usage=usage)

    async def stream(
        self,
        messages: list[dict],
        max_tokens: int = 2000,
        temperature: float = 0.7,
    ) -> StreamResult:
        body = {
            'model': self._model,
            'messages': messages,
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
        usage: TokenUsage | None = None
        async with self._client.stream('POST', '/chat/completions', json=body) as resp:
            resp.raise_for_status()
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
        result.usage = usage

    async def close(self) -> None:
        await self._client.aclose()

    async def test_connection(self) -> bool:
        try:
            resp = await self._client.get('/models')
            return resp.status_code == 200
        except httpx.HTTPError:
            return False
