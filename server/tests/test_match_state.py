"""Match-state consistency: undo and pass on a match, re-likes.

A match is shared state: while it exists, the partner must not resurface in
the deck or under /rejected, and a re-like must not claim interest was sent.
"""

import uuid

import sqlalchemy as sa

from conftest import (
    latest_match_id,
    login,
    make_profile,
    profile_for_email,
    seed_like,
    seed_user_profile,
)


def _email() -> str:
    return f"{uuid.uuid4().hex}@example.com"


async def _matched_builder(client, db):
    """Log in as a builder and match with a fresh marketer via real swipes."""
    email = _email()
    await login(client, email)
    await make_profile(client, role="builder", name="MeBuilder")
    me = await profile_for_email(db, email)
    other = await seed_user_profile(db, "marketer", "MatchedMkt")
    await seed_like(db, other.id, me.id)
    await client.post("/swipe", data={"target_id": str(other.id), "direction": "like"})
    return me, other


async def _match_count(db) -> int:
    from models import Match

    return (await db.execute(sa.select(sa.func.count()).select_from(Match))).scalar_one()


async def test_matched_partner_stays_out_of_deck_after_undo(client, db):
    """Undo of a like on a match that has messages keeps the match — and the
    partner must not come back into the deck with the swipe row gone."""
    me, other = await _matched_builder(client, db)
    match_id = await latest_match_id(db)
    r = await client.post("/intro", data={"match_id": str(match_id), "body": "hi"})
    assert r.status_code < 400

    await client.post("/undo")
    assert await _match_count(db) == 1

    deck = await client.get("/deck")
    assert deck.ok
    assert "MatchedMkt" not in deck.text


async def test_passed_match_not_under_rejected(client, db):
    """A pass/like cycle can leave a pass swipe on a matched partner — they
    stay on /matches and must not appear under /rejected."""
    me, other = await _matched_builder(client, db)
    assert await _match_count(db) == 1

    await client.post("/swipe", data={"target_id": str(other.id), "direction": "pass"})

    rejected = await client.get("/rejected")
    assert rejected.ok
    assert "MatchedMkt" not in rejected.text
    matches = await client.get("/matches")
    assert "MatchedMkt" in matches.text


async def test_relike_on_match_does_not_say_interest_sent(client, db):
    """Re-liking a partner the match already covers records the swipe without
    promising a pending interest."""
    me, other = await _matched_builder(client, db)
    assert await _match_count(db) == 1

    r = await client.post(
        "/swipe", data={"target_id": str(other.id), "direction": "like"}
    )
    assert r.ok
    assert "Interest sent" not in r.text
    assert await _match_count(db) == 1
