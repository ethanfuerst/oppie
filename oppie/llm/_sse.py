from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


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
