"""Security hardening regression tests.

Each test pins one finding from a security review so it cannot regress:
  - magic-link endpoint accepts exactly one well-formed address; the per-email
      limiter cannot be dodged with +tags or case.
  - intros are length-capped and throttled per match.
  - GET /auth/verify only renders a confirm page; POST /auth/verify signs in.
  - a magic token can be consumed exactly once, even concurrently.
  - security headers on every page; authenticated pages are not cacheable.
  - a banned user cannot sign in or keep a session; saving a profile never
      un-hides a hidden one.
  - a swipe on a profile that is not a valid target does not echo its name.
  - re-swiping like after a pass records the like.
  - profile save rejects a role outside {builder, marketer}.
  - hostile bodies get a 4xx, never a 500.
"""

import asyncio
import uuid

import sqlalchemy as sa

from conftest import (
    last_magic_link,
    login,
    make_profile,
    profile_for_email,
    seed_like,
    seed_match,
    seed_user_profile,
)


def _email() -> str:
    return f"{uuid.uuid4().hex}@example.com"


def _outbox():
    from services.email import OUTBOX

    return OUTBOX


# ---- one address per request, limiter keyed on the normalised address ----

async def test_request_link_rejects_multiple_recipients(client):
    for bad in (
        "a@example.com, b@example.com",
        "a@example.com;b@example.com",
        "a@example.com b@example.com",
        "Name <a@example.com>, b@example.com",
    ):
        r = await client.post("/auth/request-link", data={"email": bad})
        assert r.status_code in (400, 422), bad
    assert _outbox() == []


async def test_request_link_rejects_malformed_and_oversized(client):
    for bad in ("not-an-email", "@example.com", "a@", "x" * 330 + "@example.com"):
        r = await client.post("/auth/request-link", data={"email": bad})
        assert r.status_code in (400, 422), bad
    assert _outbox() == []


async def test_request_link_rejects_non_string_json_email(client):
    r = await client.post(
        "/auth/request-link",
        content=b'{"email": ["a@example.com", "b@example.com"]}',
        headers={"content-type": "application/json"},
    )
    assert r.status_code in (400, 422)
    assert _outbox() == []


async def test_email_limiter_ignores_plus_tags_and_case(client):
    local = uuid.uuid4().hex
    statuses = []
    for i in range(7):
        addr = f"{local}+{i}@Example.com" if i % 2 else f"{local.upper()}+{i}@example.com"
        r = await client.post("/auth/request-link", data={"email": addr})
        statuses.append(r.status_code)
    assert 429 in statuses
    assert len(_outbox()) <= 5


async def test_valid_address_still_gets_a_link(client):
    r = await client.post("/auth/request-link", data={"email": _email()})
    assert r.status_code in (200, 202, 204)
    assert "/auth/verify" in last_magic_link()


# ---- single-use token, atomically ----

class _SlowReads:
    """Redis proxy that yields after every plain GET, widening any check-then-delete gap."""

    def __init__(self, inner):
        self._inner = inner

    async def get(self, *a, **kw):
        value = await self._inner.get(*a, **kw)
        await asyncio.sleep(0.01)
        return value

    def __getattr__(self, name):
        return getattr(self._inner, name)


async def test_magic_token_consumed_once_under_concurrency(client, monkeypatch):
    import auth.tokens as tokens

    token = await tokens.issue_magic_link(_email())
    real = tokens.get_redis
    monkeypatch.setattr(tokens, "get_redis", lambda: _SlowReads(real()))
    results = await asyncio.gather(*(tokens.consume_magic_token(token) for _ in range(5)))
    assert sum(1 for x in results if x) == 1


# ---- GET is a confirm page, POST signs in ----

def _session_cookie(client) -> bool:
    return any("session" in k.lower() for k in client.cookies.keys())


def _verify_path() -> str:
    link = last_magic_link()
    return link.split("testserver", 1)[-1] if "testserver" in link else link


async def test_get_verify_does_not_sign_in_or_burn_token(client):
    await client.post("/auth/request-link", data={"email": _email()})
    path = _verify_path()
    token = path.split("token=", 1)[1]

    # A mail scanner prefetching the link twice must neither sign in nor consume it.
    for _ in range(2):
        r = await client.get(path)
        assert r.status_code == 200
        assert not _session_cookie(client)
        assert 'method="post"' in r.text.lower()

    r = await client.post("/auth/verify", data={"token": token}, follow_redirects=False)
    assert r.status_code in (302, 303)
    assert _session_cookie(client)


async def test_post_verify_rejects_reused_token(client):
    await client.post("/auth/request-link", data={"email": _email()})
    token = _verify_path().split("token=", 1)[1]
    r1 = await client.post("/auth/verify", data={"token": token}, follow_redirects=False)
    assert r1.status_code in (302, 303)
    await client.post("/auth/logout")
    r2 = await client.post("/auth/verify", data={"token": token})
    assert r2.status_code in (400, 401, 403)


async def test_post_verify_rejects_garbage(client):
    r = await client.post("/auth/verify", data={"token": "garbage"})
    assert r.status_code in (400, 401, 403)
    assert not _session_cookie(client)


# ---- intro cap + throttle ----

async def _matched_pair(client, db):
    email = _email()
    await login(client, email)
    await make_profile(client, role="builder", name="Me")
    me = await profile_for_email(db, email)
    other = await seed_user_profile(db, "marketer", "Them")
    m = await seed_match(db, me.id, other.id)
    return me, other, m


async def _message_count(db) -> int:
    from models import Message

    return (await db.execute(sa.select(sa.func.count()).select_from(Message))).scalar_one()


async def test_intro_body_is_length_capped(client, db):
    _, _, m = await _matched_pair(client, db)
    sent_before = len(_outbox())  # login() leaves its magic-link mail here
    r = await client.post("/intro", data={"match_id": str(m.id), "body": "x" * 2001})
    assert r.status_code in (400, 413, 422)
    assert await _message_count(db) == 0
    assert len(_outbox()) == sent_before


async def test_intro_is_throttled_per_match(client, db):
    _, _, m = await _matched_pair(client, db)
    statuses = []
    for i in range(8):
        r = await client.post("/intro", data={"match_id": str(m.id), "body": f"hello {i}"})
        statuses.append(r.status_code)
    assert 429 in statuses
    assert await _message_count(db) <= 5


# ---- headers ----

async def test_security_headers_on_public_page(client):
    r = await client.get("/")
    h = r.headers  # case-insensitive, str keys
    assert h.get("x-content-type-options") == "nosniff"
    assert h.get("referrer-policy")
    assert (h.get("x-frame-options") or "").upper() in ("DENY", "SAMEORIGIN") or (
        "frame-ancestors" in (h.get("content-security-policy") or "")
    )


async def test_authenticated_pages_are_not_cacheable(client, db):
    email = _email()
    await login(client, email)
    await make_profile(client)
    for path in ("/profile", "/account/export", "/matches"):
        r = await client.get(path)
        cc = r.headers.get("cache-control", "")
        assert "no-store" in cc, path


# ---- moderation fields are respected ----

async def test_banned_user_session_stops_working(client, db):
    from models import User

    email = _email()
    await login(client, email)
    await make_profile(client)
    await db.execute(sa.update(User).where(User.email == email).values(status="banned"))
    await db.commit()
    r = await client.get("/profile")
    assert r.status_code in (302, 303, 401, 403)


async def test_banned_user_cannot_sign_in(client, db):
    from models import User

    email = _email()
    db.add(User(email=email, status="banned"))
    await db.commit()
    await client.post("/auth/request-link", data={"email": email})
    link = last_magic_link()
    if link:
        token = link.split("token=", 1)[1]
        r = await client.post("/auth/verify", data={"token": token})
        assert r.status_code in (400, 401, 403)
    assert not _session_cookie(client)


async def test_saving_profile_does_not_unhide_it(client, db):
    from models import Profile

    email = _email()
    await login(client, email)
    await make_profile(client)
    me = await profile_for_email(db, email)
    await db.execute(sa.update(Profile).where(Profile.id == me.id).values(visibility="hidden"))
    await db.commit()
    await make_profile(client, bio="edited bio")
    db.expire_all()
    me = await profile_for_email(db, email)
    assert me.visibility == "hidden"


# ---- no name oracle ----

async def test_swipe_on_invalid_target_does_not_echo_name(client, db):
    email = _email()
    await login(client, email)
    await make_profile(client, role="builder")
    same_side = await seed_user_profile(db, "builder", "ZzSecretSameSideName")
    r = await client.post("/swipe", data={"target_id": str(same_side.id), "direction": "like"})
    assert "ZzSecretSameSideName" not in (r.text or "")


# ---- re-swipe after pass ----

async def test_like_after_pass_is_recorded_and_matches(client, db):
    from models import Match, Swipe

    email = _email()
    await login(client, email)
    await make_profile(client, role="builder")
    me_id = (await profile_for_email(db, email)).id
    other_id = (await seed_user_profile(db, "marketer", "Other")).id
    db.add(Swipe(swiper_profile_id=me_id, target_profile_id=other_id, direction="pass"))
    await db.commit()
    await seed_like(db, other_id, me_id)

    await client.post("/swipe", data={"target_id": str(other_id), "direction": "like"})
    db.expire_all()
    s = (await db.execute(
        sa.select(Swipe).where(Swipe.swiper_profile_id == me_id, Swipe.target_profile_id == other_id)
    )).scalar_one()
    assert s.direction == "like"
    assert (await db.execute(sa.select(sa.func.count()).select_from(Match))).scalar_one() == 1


# ---- role whitelist on profile save ----

async def test_profile_save_rejects_unknown_role(client, db):
    email = _email()
    await login(client, email)
    await make_profile(client, role="builder")
    await make_profile(client, role="admin")
    me = await profile_for_email(db, email)
    await db.refresh(me)
    assert me.role == "builder"


# ---- hostile bodies are 4xx ----

async def test_hostile_bodies_are_client_errors(client, db):
    email = _email()
    await login(client, email)
    await make_profile(client)
    r = await client.post(
        "/swipe", content=b"{not json", headers={"content-type": "application/json"}
    )
    assert 400 <= r.status_code < 500
    r = await client.post(
        "/auth/request-link",
        content=b"email=\xff\xfe@example.com",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert 400 <= r.status_code < 500
    r = await make_profile(client, name="n" * 300)
    assert r.status_code < 500
