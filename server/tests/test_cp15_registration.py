"""Checkpoint 15 — landing registration (role + name + email) [2026-06-25].

The landing hero IS the registration: a visitor picks a side (builder/marketer),
types their name and email, and submits. That posts role + name alongside the
email to /auth/request-link. When they click the magic link, verifying creates
their profile from the stashed role + name, so they land on a working deck — no
separate "create a profile" step.

Backward compatible: an email-only login (the cp2 flow, no role/name) must NOT
fabricate a profile.
"""

import uuid

import sqlalchemy as sa

from conftest import last_magic_link, login, seed_user_profile


async def _register(client, email, role, name):
    await client.post("/auth/request-link", json={"email": email, "role": role, "name": name})
    link = last_magic_link()
    assert link, "registration must still send a magic link"
    path = link.split("testserver", 1)[-1] if "testserver" in link else link
    token = path.split("token=", 1)[1]
    await client.get(path)  # the confirm page; sign-in happens on POST
    return await client.post("/auth/verify", data={"token": token})


async def _profile_for(db, email):
    from models import Profile, User

    return (await db.execute(
        sa.select(Profile).join(User, Profile.user_id == User.id).where(User.email == email)
    )).scalar_one_or_none()


async def test_registration_creates_profile_on_verify(client, db):
    email = f"{uuid.uuid4().hex}@example.com"
    r = await _register(client, email, "builder", "RegBuilder")
    assert r.status_code in (200, 303)

    prof = await _profile_for(db, email)
    assert prof is not None, "verifying a registration must create the profile"
    assert prof.role == "builder"
    assert prof.name == "RegBuilder"
    assert prof.visibility == "live", "registered profile must be live (discoverable)"


async def test_registration_role_drives_deck(client, db):
    await seed_user_profile(db, role="marketer", name="DeckMktForReg")
    email = f"{uuid.uuid4().hex}@example.com"
    await _register(client, email, "builder", "RegBuilder2")

    r = await client.get("/deck")
    assert r.status_code == 200, "a freshly registered user lands on a working deck"
    assert "DeckMktForReg" in r.text, "builder registrant must see marketer candidates"


async def test_plain_login_creates_no_profile(client, db):
    email = f"{uuid.uuid4().hex}@example.com"
    await login(client, email)  # email only, no role/name (cp2 flow)
    assert await _profile_for(db, email) is None, \
        "email-only login must not fabricate a profile"
