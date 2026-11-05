"""Shared async Redis connection (one client per running event loop)."""

from __future__ import annotations

import asyncio

import redis.asyncio as redis

from config import settings

_pools: dict[int, redis.Redis] = {}


def get_redis() -> redis.Redis:
    """Return the shared async Redis client, created on first use."""
    loop = asyncio.get_running_loop()
    key = id(loop)
    client = _pools.get(key)
    if client is None:
        client = redis.from_url(settings.redis_url, decode_responses=True)
        _pools[key] = client
    return client