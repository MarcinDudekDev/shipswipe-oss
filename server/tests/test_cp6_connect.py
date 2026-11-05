"""Checkpoint 6 — connect + send intro (the payoff).

POST /connect  {match_id}            -> marks the match connected, reveals contact context
POST /intro    {match_id, body}      -> persists a Message, notifies the other party,
                                        confirms; an EMPTY intro is rejected (no message,
                                        no success). You may only act on YOUR OWN match.
"""

import uuid

import sqlalchemy as sa

from conftest import (
    login, make_profile, profile_for_email, seed_user_profile, seed_like,
    seed_match, latest_match_id,
)


async def _make_match(client, db):
    """Log in builder A, create a real mutual match with marketer B. Returns (a, b, match_id)."""
    email = f"{uuid.uuid4().hex}@example.com"
    await login(client, email)
    await make_profile(client, role="builder", name="PriyaBuilder")
    a = await profile_for_email(db, email)
    b = await seed_user_profile(db, role="marketer", name="ConnectMkt", terms="equity")
    await seed_like(db, b.id, a.id)
    await client.post("/swipe", data={"target_id": str(b.id), "direction": "like"})
    mid = await latest_match_id(db)
    assert mid is not None
    return a, b, mid


async def test_connect_marks_connected(client, db):
    a, b, mid = await _make_match(client, db)
    r = await client.post("/connect", data={"match_id": str(mid)})
    assert r.ok

    from models import Match
    m = await db.get(Match, mid)
    assert m.connected_at is not None


async def test_send_intro_persists_message(client, db):
    a, b, mid = await _make_match(client, db)
    r = await client.post("/intro", data={"match_id": str(mid), "body": "Hi! Loved your channels — want to talk launch?"})
    assert r.ok

    from models import Message
    cnt = (await db.execute(sa.select(sa.func.count()).select_from(Message)
                            .where(Message.match_id == mid))).scalar()
    assert cnt == 1


async def test_send_intro_notifies_other_party(client, db):
    a, b, mid = await _make_match(client, db)
    from services.email import OUTBOX
    before = len(OUTBOX)
    await client.post("/intro", data={"match_id": str(mid), "body": "intro text here"})
    assert len(OUTBOX) > before


async def test_empty_intro_is_rejected(client, db):
    a, b, mid = await _make_match(client, db)
    r = await client.post("/intro", data={"match_id": str(mid), "body": "   "})
    # no message stored, and not reported as a success
    from models import Message
    cnt = (await db.execute(sa.select(sa.func.count()).select_from(Message)
                            .where(Message.match_id == mid))).scalar()
    assert cnt == 0
    assert r.status_code in (400, 422) or "sent" not in (r.text or "").lower()


async def test_cannot_intro_on_someone_elses_match(client, db):
    """A logged-in user must not send an intro on a match they are not part of."""
    email = f"{uuid.uuid4().hex}@example.com"
    await login(client, email)
    await make_profile(client, role="builder", name="OutsiderBuilder")

    # a match between two unrelated profiles
    x = await seed_user_profile(db, role="builder", name="StrangerA")
    y = await seed_user_profile(db, role="marketer", name="StrangerB")
    m = await seed_match(db, x.id, y.id)

    r = await client.post("/intro", data={"match_id": str(m.id), "body": "let me in"})
    assert r.status_code in (401, 403, 404)
    from models import Message
    cnt = (await db.execute(sa.select(sa.func.count()).select_from(Message)
                            .where(Message.match_id == m.id))).scalar()
    assert cnt == 0
