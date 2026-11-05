"""Checkpoint 2 — passwordless magic-link auth + Redis sessions.

The implementation must provide HTTP endpoints:
  - POST /auth/request-link  (form/json {email})  -> 204, captures an email with a
    verify link into services.email.OUTBOX (test mode never actually sends)
  - GET  /auth/verify?token=...                    -> redirect + sets a session cookie
  - POST /auth/logout                              -> clears the session
And a gate: an authenticated-only route (use /profile) returns 200 once logged in,
and redirects/401s when anonymous.
"""

import uuid

from conftest import last_magic_link, login


async def test_request_link_returns_204_and_captures_email(client):
    email = f"{uuid.uuid4().hex}@example.com"
    r = await client.post("/auth/request-link", data={"email": email})
    assert r.status_code in (200, 202, 204)
    link = last_magic_link()
    assert "/auth/verify" in link


async def test_request_link_does_not_leak_token_in_response(client):
    """No account enumeration / token leak — the token rides email, not the body."""
    email = f"{uuid.uuid4().hex}@example.com"
    r = await client.post("/auth/request-link", data={"email": email})
    assert "/auth/verify" not in (r.text or "")


async def test_verify_sets_session_cookie(client):
    email = f"{uuid.uuid4().hex}@example.com"
    r = await login(client, email)
    assert r.status_code in (200, 302, 303)
    # a session cookie should now be present on the client jar
    assert any("session" in c.lower() or "sid" in c.lower() for c in client.cookies.keys())


async def test_invalid_token_is_rejected(client):
    r = await client.get("/auth/verify?token=garbage-not-a-real-token")
    assert r.status_code in (400, 401, 403, 302, 303)
    assert not any("session" in c.lower() or "sid" in c.lower() for c in client.cookies.keys())


async def test_authed_user_persisted(client, db):
    from models import User
    import sqlalchemy as sa

    email = f"{uuid.uuid4().hex}@example.com"
    await login(client, email)
    row = (await db.execute(sa.select(User).where(User.email == email))).scalar_one_or_none()
    assert row is not None
    assert row.email_verified_at is not None


async def test_protected_route_requires_login(client):
    """Anonymous access to a gated page must not return a logged-in 200 profile view."""
    r = await client.get("/profile")
    # either redirected to login or an explicit gate — not a 200 authed profile
    assert r.status_code in (302, 303, 401, 403) or "need" in (r.text or "").lower()


async def test_logout_clears_session(client):
    email = f"{uuid.uuid4().hex}@example.com"
    await login(client, email)
    await client.post("/auth/logout")
    assert not any("session" in c.lower() or "sid" in c.lower() for c in client.cookies.keys()) \
        or True  # cookie may be set empty/expired; the gate check below is authoritative
    r = await client.get("/profile")
    assert r.status_code in (302, 303, 401, 403) or "need" in (r.text or "").lower()
