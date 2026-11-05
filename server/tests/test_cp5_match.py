"""Checkpoint 5 — mutual match + notification.

When you LIKE someone who already liked you, a Match is created (atomically, deduped),
both parties get an email notification (captured in OUTBOX in test mode), and the
match appears on GET /matches. A one-sided like creates NO match.
"""

import uuid

import sqlalchemy as sa

from conftest import (
    login, make_profile, profile_for_email, seed_user_profile, seed_like,
)


async def _builder_and_pre_liker(client, db):
    """Log in builder A, give A a profile, seed marketer B who already liked A."""
    email = f"{uuid.uuid4().hex}@example.com"
    await login(client, email)
    await make_profile(client, role="builder", name="MayaBuilder")
    a = await profile_for_email(db, email)
    b = await seed_user_profile(db, role="marketer", name="ElenaMatch", terms="rev-share")
    await seed_like(db, b.id, a.id)  # B liked A first
    return a, b


async def test_mutual_like_creates_match(client, db):
    a, b = await _builder_and_pre_liker(client, db)
    r = await client.post("/swipe", data={"target_id": str(b.id), "direction": "like"})
    assert r.ok or r.status_code in (200, 204)

    from models import Match
    cnt = (await db.execute(sa.select(sa.func.count()).select_from(Match))).scalar()
    assert cnt == 1


async def test_match_sends_notification(client, db):
    a, b = await _builder_and_pre_liker(client, db)
    from services.email import OUTBOX
    before = len(OUTBOX)
    await client.post("/swipe", data={"target_id": str(b.id), "direction": "like"})
    assert len(OUTBOX) > before
    assert any("match" in (m.get("subject", "") + m.get("body", "")).lower() for m in OUTBOX)


async def test_match_listed_on_matches_page(client, db):
    a, b = await _builder_and_pre_liker(client, db)
    await client.post("/swipe", data={"target_id": str(b.id), "direction": "like"})
    r = await client.get("/matches")
    assert r.ok
    assert "ElenaMatch" in r.text


async def test_one_sided_like_is_not_a_match(client, db):
    email = f"{uuid.uuid4().hex}@example.com"
    await login(client, email)
    await make_profile(client, role="builder", name="LonelyBuilder")
    b = await seed_user_profile(db, role="marketer", name="NoReplyMkt")

    await client.post("/swipe", data={"target_id": str(b.id), "direction": "like"})
    from models import Match
    cnt = (await db.execute(sa.select(sa.func.count()).select_from(Match))).scalar()
    assert cnt == 0


async def test_match_is_idempotent(client, db):
    """Re-evaluating the same pair must not create a duplicate match row."""
    a, b = await _builder_and_pre_liker(client, db)
    await client.post("/swipe", data={"target_id": str(b.id), "direction": "like"})
    # a second like on the same target must not double-insert
    await client.post("/swipe", data={"target_id": str(b.id), "direction": "like"})
    from models import Match
    cnt = (await db.execute(sa.select(sa.func.count()).select_from(Match))).scalar()
    assert cnt == 1
