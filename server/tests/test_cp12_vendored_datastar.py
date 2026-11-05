"""Checkpoint 12 — vendor the Datastar runtime locally (no CDN).

Build rule: no external network resources at runtime. The deck page must load
Datastar from our own /static, not jsdelivr. So:
  - GET /static/js/datastar.js serves the real bundle (200, sizeable, Datastar code)
  - the discover page references that LOCAL path and NOT a CDN
"""

import uuid

from conftest import login, make_profile, seed_user_profile


async def test_datastar_bundle_served_locally(client, db):
    r = await client.get("/static/js/datastar.js")
    assert r.status_code == 200, "the Datastar runtime must be vendored under /static"
    assert len(r.text) > 20000, "must be the real Datastar bundle, not a stub"
    assert "datastar" in r.text.lower(), "served file must actually be Datastar"


async def test_discover_uses_local_datastar_not_cdn(client, db):
    await seed_user_profile(db, role="marketer", name="VendorMkt")
    await login(client, f"{uuid.uuid4().hex}@example.com")
    await make_profile(client, role="builder", name="MeVendor")
    r = await client.get("/discover")
    assert r.status_code == 200
    assert "/static/js/datastar.js" in r.text, "page must load the local Datastar bundle"
    assert "jsdelivr" not in r.text and "cdn." not in r.text, "no CDN runtime allowed"
