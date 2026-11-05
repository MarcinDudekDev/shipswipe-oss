"""Account deletion and undo stay correct under concurrency.

Deleting an account while someone swipes on it, messages it, or while the
owner saves their profile must never produce a 500; an undo racing the
partner's like must never leave a match without both likes.
"""

import asyncio
import uuid

import sqlalchemy as sa

from conftest import login, make_profile, profile_for_email, seed_like, seed_match


def _email() -> str:
    return f"{uuid.uuid4().hex}@example.com"


async def _pair(db):
    """Two logged-in clients: a builder (the deleter) and a marketer, already matched."""
    import main
    from stario.testing import TestClient

    a_ctx, b_ctx = TestClient(main.bootstrap), TestClient(main.bootstrap)
    a, b = await a_ctx.__aenter__(), await b_ctx.__aenter__()
    ea, eb = _email(), _email()
    await login(a, ea)
    await make_profile(a, role="builder", name="A")
    await login(b, eb)
    await make_profile(b, role="marketer", name="B")
    ida = (await profile_for_email(db, ea)).id
    idb = (await profile_for_email(db, eb)).id
    return (a, a_ctx), (b, b_ctx), ida, idb


async def _close(*ctxs):
    for c in ctxs:
        await c.__aexit__(None, None, None)


async def test_delete_racing_partner_activity_never_crashes(db, schema):
    for _ in range(6):
        (a, a_ctx), (b, b_ctx), ida, idb = await _pair(db)
        m = await seed_match(db, ida, idb)
        rs = await asyncio.gather(
            a.post("/account/delete", data={"confirm": "DELETE"}),
            b.post("/swipe", data={"target_id": str(ida), "direction": "like"}),
            b.post("/intro", data={"match_id": str(m.id), "body": "hi"}),
            a.post("/profile", data={"role": "builder", "name": "A", "bio": "b",
                                     "building": "x", "looking_for": "y",
                                     "terms": "rev-share", "tags": "a,b"}),
        )
        await _close(a_ctx, b_ctx)
        assert all(r.status_code < 500 for r in rs), [r.status_code for r in rs]


async def test_undo_racing_partner_like_leaves_no_phantom_match(db, schema):
    from models import Match, Swipe

    for _ in range(10):
        (a, a_ctx), (b, b_ctx), ida, idb = await _pair(db)
        await seed_like(db, idb, ida)  # B already likes A
        await b.post("/swipe", data={"target_id": str(ida), "direction": "like"})
        await asyncio.gather(
            a.post("/swipe", data={"target_id": str(idb), "direction": "like"}),
            b.post("/undo"),
        )
        await _close(a_ctx, b_ctx)
        db.expire_all()
        matched = (await db.execute(
            sa.select(sa.func.count()).select_from(Match).where(
                sa.or_(sa.and_(Match.profile_a_id == ida, Match.profile_b_id == idb),
                       sa.and_(Match.profile_a_id == idb, Match.profile_b_id == ida))
            )
        )).scalar_one()
        b_likes = (await db.execute(
            sa.select(sa.func.count()).select_from(Swipe).where(
                Swipe.swiper_profile_id == idb, Swipe.target_profile_id == ida,
                Swipe.direction == "like",
            )
        )).scalar_one()
        if matched:
            assert b_likes == 1, "match exists although B's like was undone"
