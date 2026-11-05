"""Checkpoint 3 — create / edit YOUR profile.

POST /profile (authed) creates-or-updates the current user's Profile from form fields
role,name,bio,building,looking_for,terms,tags. GET /profile reflects them back.
Role-aware: a builder's deck is marketers and vice-versa (rebuild on role change).
"""

import uuid

from conftest import login, make_profile, profile_for_email


async def test_create_profile_persists(client, db):
    email = f"{uuid.uuid4().hex}@example.com"
    await login(client, email)
    r = await make_profile(client, role="builder", name="Maya", building="B2B invoicing tool")
    assert r.status_code in (200, 201, 303)

    p = await profile_for_email(db, email)
    assert p is not None
    assert p.role == "builder"
    assert p.building == "B2B invoicing tool"


async def test_get_profile_shows_fields(client):
    email = f"{uuid.uuid4().hex}@example.com"
    await login(client, email)
    await make_profile(client, name="Jonas", building="open-source API analytics")
    r = await client.get("/profile")
    assert r.ok
    assert "Jonas" in r.text and "open-source API analytics" in r.text


async def test_update_profile_overwrites(client, db):
    email = f"{uuid.uuid4().hex}@example.com"
    await login(client, email)
    await make_profile(client, role="builder", terms="rev-share")
    await make_profile(client, role="builder", terms="equity", building="changed thing")

    p = await profile_for_email(db, email)
    assert p.terms == "equity"
    assert p.building == "changed thing"


async def test_create_profile_requires_login(client):
    r = await make_profile(client, name="Anon")
    assert r.status_code in (302, 303, 401, 403)
