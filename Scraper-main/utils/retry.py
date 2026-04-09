from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, TypeVar


T = TypeVar("T")


async def with_retry(
    fn: Callable[[], Awaitable[T]],
    retries: int = 3,
    base_delay: float = 0.5,
) -> T:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            return await fn()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt == retries - 1:
                break
            await asyncio.sleep(base_delay * (2 ** attempt))
    raise RuntimeError(f"Operation failed after {retries} retries") from last_error
