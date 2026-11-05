"""Checkpoint 0 smoke tests — scaffold serves home, health, and static assets."""

import pytest

from stario.testing import TestClient

import main


@pytest.mark.asyncio
async def test_home_ok():
    async with TestClient(main.bootstrap) as client:
        r = await client.get("/")
        assert r.ok
        assert "ShipSwipe" in r.text


@pytest.mark.asyncio
async def test_healthz_json():
    async with TestClient(main.bootstrap) as client:
        r = await client.get("/healthz")
        assert r.ok
        assert r.json() == {"status": "ok", "service": "shipswipe-server"}


@pytest.mark.asyncio
async def test_static_styles_served():
    async with TestClient(main.bootstrap) as client:
        r = await client.get("/static/styles.css")
        assert r.ok
        assert len(r.content) > 1000
