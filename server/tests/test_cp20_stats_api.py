"""Checkpoint 20 — live stats API + animated counters [2026-06-29].

The homepage counters animate up on load and refresh themselves without a full
reload by polling a JSON endpoint, so the numbers stay accurate/live.

  GET /api/stats -> {"builders": N, "marketers": N, "matches": N}
  GET /          -> loads the counter animator script
"""

import json

from conftest import seed_match, seed_user_profile


async def test_stats_api_returns_live_counts(client, db):
    b1 = await seed_user_profile(db, role="builder", name="ApiB1")
    await seed_user_profile(db, role="marketer", name="ApiM1")
    await seed_user_profile(db, role="marketer", name="ApiM2")
    m1 = await seed_user_profile(db, role="marketer", name="ApiM3")
    await seed_match(db, b1.id, m1.id)

    r = await client.get("/api/stats")
    assert r.status_code == 200
    assert "application/json" in r.headers.get("content-type", "")
    data = json.loads(r.text)
    assert data["builders"] == 1
    assert data["marketers"] == 3
    assert data["matches"] == 1


async def test_homepage_loads_counter_animator(client):
    r = await client.get("/")
    assert "/static/js/stats.js" in r.text, "homepage must load the counter animator"
