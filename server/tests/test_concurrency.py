"""Concurrent requests stay correct and never produce a 500.

Covers parallel saves of one profile, simultaneous mutual likes (which must
still produce exactly one match), an intro racing an undo, and the origin
check on authenticated POSTs.
"""

import asyncio
import uuid

import sqlalchemy as sa

from conftest import login, make_profile, profile_for_email, seed_match, seed_user_profile


def _email() -> str:
    return f"{uuid.uuid4().hex}@example.com"


async def test_parallel_profile_saves_never_crash(client, db):
    await login(client, _email())
    rs = await asyncio.gather(*(make_profile(client, tags=f"a,b,c{i}") for i in range(8)))
    assert all(r.status_code < 500 for r in rs), [r.status_code for r in rs]


async def test_first_profile_save_in_parallel_never_crashes(client, db):
    await login(client, _email())
    rs = await asyncio.gather(*(make_profile(client) for _ in range(6)))
    assert all(r.status_code < 500 for r in rs), [r.status_code for r in rs]


async def test_simultaneous_mutual_likes_always_match(db, schema):
    """Two users like each other at the same moment: exactly one match, every time."""
    import main
    from models import Match
    from stario.testing import TestClient

    for _ in range(5):
        async with TestClient(main.bootstrap) as a, TestClient(main.bootstrap) as b:
            ea, eb = _email(), _email()
            await login(a, ea)
            await make_profile(a, role="builder", name="A")
            await login(b, eb)
            await make_profile(b, role="marketer", name="B")
            ida = (await profile_for_email(db, ea)).id
            idb = (await profile_for_email(db, eb)).id
            ra, rb = await asyncio.gather(
                a.post("/swipe", data={"target_id": str(idb), "direction": "like"}),
                b.post("/swipe", data={"target_id": str(ida), "direction": "like"}),
            )
            assert ra.status_code < 500 and rb.status_code < 500
            db.expire_all()
            n = (await db.execute(
                sa.select(sa.func.count()).select_from(Match).where(
                    sa.or_(Match.profile_a_id.in_([ida, idb]),
                           Match.profile_b_id.in_([ida, idb]))
                )
            )).scalar_one()
            assert n == 1


async def test_intro_racing_undo_never_crashes(client, db):
    email = _email()
    await login(client, email)
    await make_profile(client, role="builder", name="Me")
    me = await profile_for_email(db, email)
    for _ in range(5):
        other = await seed_user_profile(db, "marketer", "Other")
        await client.post("/swipe", data={"target_id": str(other.id), "direction": "like"})
        m = await seed_match(db, me.id, other.id)
        rs = await asyncio.gather(
            client.post("/intro", data={"match_id": str(m.id), "body": "hi"}),
            client.post("/undo"),
        )
        assert all(r.status_code < 500 for r in rs), [r.status_code for r in rs]


async def test_authenticated_posts_refuse_foreign_origin(client, db):
    email = _email()
    await login(client, email)
    await make_profile(client, bio="original")
    for headers in (
        {"origin": "https://evil.example"},
        {"sec-fetch-site": "cross-site"},
        {"sec-fetch-site": "same-site", "origin": "https://sub.testserver"},
    ):
        r = await client.post(
            "/profile",
            data={"role": "builder", "name": "Me", "bio": "pwned", "building": "x",
                  "looking_for": "y", "terms": "rev-share", "tags": "a"},
            headers=headers,
        )
        assert r.status_code == 403, headers
    me = await profile_for_email(db, email)
    await db.refresh(me)
    assert me.bio == "original"


async def test_same_origin_authenticated_post_still_works(client, db):
    email = _email()
    await login(client, email)
    r = await client.post(
        "/profile",
        data={"role": "builder", "name": "Me", "bio": "ok", "building": "x",
              "looking_for": "y", "terms": "rev-share", "tags": "a"},
        headers={"origin": "http://testserver", "sec-fetch-site": "same-origin"},
    )
    assert r.status_code < 400


async def test_body_cap_is_64_kb(client):
    small = b"email=" + b"a" * 60_000
    big = b"email=" + b"a" * 70_000
    ct = {"content-type": "application/x-www-form-urlencoded"}
    assert (await client.post("/auth/request-link", content=small, headers=ct)).status_code != 413
    assert (await client.post("/auth/request-link", content=big, headers=ct)).status_code == 413
