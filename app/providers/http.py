import asyncio
import random
from typing import Any

import httpx


async def request(
    client: httpx.AsyncClient, method: str, url: str, **kwargs: Any
) -> httpx.Response:
    """Retry only timeouts, throttling and server failures, at most three attempts."""
    for attempt in range(3):
        try:
            response = await client.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
            retryable = isinstance(exc, httpx.TimeoutException) or (
                exc.response.status_code == 429 or exc.response.status_code >= 500
            )
            if not retryable or attempt == 2:
                raise
            await asyncio.sleep(2**attempt + random.uniform(0, 0.5))
    raise AssertionError("unreachable")
