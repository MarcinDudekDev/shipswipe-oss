"""Checkpoint 22 — industry labels + reconsider a rejected profile.

Early-user feedback (2026-06-30): "Pass" read as approval (industry jargon) when it
meant decline. Buttons now say Reject / Interested, and rejected profiles get a
dedicated page where they can be sent back to the deck.

GET  /rejected     -> lists profiles this user rejected (direction == "pass")
POST /reconsider   -> removes that rejection; the profile returns to /deck
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


async def test_deck_uses_industry_labels_not_dating_jargon(client, db):
    await _setup_builder(client, db)
    await seed_user_profile(db, role="marketer", name="LabelMkt")

    r = await client.get("/deck")
    assert r.ok
    assert "Reject" in r.text
    assert "Interested" in r.text
    assert ">Pass<" not in r.text  # the ambiguous label is gone


async def test_rejected_profile_appears_on_rejected_page(client, db):
    await _setup_builder(client, db)
    target = await seed_user_profile(db, role="marketer", name="RejectedMkt")

    await client.post("/swipe", data={"target_id": str(target.id), "direction": "pass"})

    r = await client.get("/rejected")
    assert r.ok
    assert "RejectedMkt" in r.text
    assert "Reconsider" in r.text


async def test_liked_profile_does_not_appear_on_rejected_page(client, db):
    await _setup_builder(client, db)
    target = await seed_user_profile(db, role="marketer", name="LikedMkt")

    await client.post("/swipe", data={"target_id": str(target.id), "direction": "like"})

    r = await client.get("/rejected")
    assert r.ok
    assert "LikedMkt" not in r.text


async def test_reconsider_returns_profile_to_deck(client, db):
    await _setup_builder(client, db)
    target = await seed_user_profile(db, role="marketer", name="ComebackMkt")

    await client.post("/swipe", data={"target_id": str(target.id), "direction": "pass"})
    # gone from the deck after a reject
    assert "ComebackMkt" not in (await client.get("/deck")).text

    r = await client.post("/reconsider", data={"target_id": str(target.id)})
    assert r.ok or r.status_code in (200, 204)

    from models import Swipe
    cnt = (await db.execute(sa.select(sa.func.count()).select_from(Swipe)
                            .where(Swipe.target_profile_id == target.id))).scalar()
    assert cnt == 0  # the rejection swipe was removed

    # back on the deck, off the rejected page
    assert "ComebackMkt" in (await client.get("/deck")).text
    assert "ComebackMkt" not in (await client.get("/rejected")).text


async def test_reconsider_requires_login(client, db):
    target = await seed_user_profile(db, role="marketer", name="GatekeptReconsider")
    r = await client.post("/reconsider", data={"target_id": str(target.id)})
    assert r.status_code in (302, 303, 401, 403)
