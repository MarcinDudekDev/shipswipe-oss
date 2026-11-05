"""Fixed-window rate limiting on the shared Redis client."""

from __future__ import annotations

from auth.redis_client import get_redis


async def rate_limited(key: str, max_hits: int, window: int) -> bool:
    """Fixed-window Redis counter. True when this hit exceeds the allowance."""
    r = get_redis()
    # SET NX seeds the counter and its TTL in one atomic step: a crash between
    # INCR and EXPIRE could otherwise leave a key that counts hits forever.
    await r.set(key, 0, ex=window, nx=True)
    hits = await r.incr(key)
    return hits > max_hits
