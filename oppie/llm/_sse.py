import json
from collections.abc import AsyncIterator
from typing import Any

import httpx


async def parse_sse_events(response: httpx.Response) -> AsyncIterator[dict[str, Any]]:
    """Parse Server-Sent Events from an httpx streaming response.

    Yield parsed JSON objects from 'data:' lines, skipping empty lines,
    comments, and the '[DONE]' sentinel.
    """
    async for line in response.aiter_lines():
        if not line or line.startswith(':'):
            continue
        if line.startswith('data: '):
            data = line[6:]
            if data.strip() == '[DONE]':
                return
            yield json.loads(data)
