"""Checkpoint 4 — discover deck + swipe + undo + filter.

GET  /deck            -> opposite-role, live, not-self, not-already-swiped candidates
POST /swipe           -> form {target_id, direction in like|pass}; records a Swipe
POST /undo            -> removes the most recent swipe (card returns to the deck)
GET  /deck?filter=... -> 'all' | 'terms:<t>' | 'tag:<T>' narrows the deck
"""

import uuid

import sqlalchemy as sa

from conftest import login, make_profile, profile_for_email, seed_user_profile


async def _setup_builder(client, db):
    email = f"{uuid.uuid4().hex}@example.com"
    await login(client, email)
    await make_profile(client, role="builder", name="MeBuilder")
    me = await profile_for_email(db, email)
    return email, me


async def test_deck_shows_opposite_role_only(client, db):
    await _setup_builder(client, db)
    await seed_user_profile(db, role="marketer", name="ElenaMkt")
    await seed_user_profile(db, role="builder", name="OtherBuilder")

    r = await client.get("/deck")
    assert r.ok
    assert "ElenaMkt" in r.text          # opposite role -> shown
    assert "OtherBuilder" not in r.text  # same role -> hidden


async def test_swipe_records_and_removes_from_deck(client, db):
    await _setup_builder(client, db)
    target = await seed_user_profile(db, role="marketer", name="MarcusMkt")

    r = await client.post("/swipe", data={"target_id": str(target.id), "direction": "pass"})
    assert r.ok or r.status_code in (200, 204)

    from models import Swipe
    cnt = (await db.execute(sa.select(sa.func.count()).select_from(Swipe)
                            .where(Swipe.target_profile_id == target.id))).scalar()
    assert cnt == 1

    r2 = await client.get("/deck")
    assert "MarcusMkt" not in r2.text


async def test_undo_restores_card(client, db):
    await _setup_builder(client, db)
    target = await seed_user_profile(db, role="marketer", name="AishaMkt")

    await client.post("/swipe", data={"target_id": str(target.id), "direction": "pass"})
    await client.post("/undo")

    from models import Swipe
    cnt = (await db.execute(sa.select(sa.func.count()).select_from(Swipe)
                            .where(Swipe.target_profile_id == target.id))).scalar()
    assert cnt == 0
    r = await client.get("/deck")
    assert "AishaMkt" in r.text


async def test_filter_by_terms(client, db):
    await _setup_builder(client, db)
    await seed_user_profile(db, role="marketer", name="RevShareMkt", terms="rev-share")
    await seed_user_profile(db, role="marketer", name="EquityMkt", terms="equity")

    r = await client.get("/deck?filter=terms:rev-share")
    assert r.ok
    assert "RevShareMkt" in r.text
    assert "EquityMkt" not in r.text


async def test_swipe_requires_login(client, db):
    target = await seed_user_profile(db, role="marketer", name="Gatekept")
    r = await client.post("/swipe", data={"target_id": str(target.id), "direction": "like"})
    assert r.status_code in (302, 303, 401, 403)
