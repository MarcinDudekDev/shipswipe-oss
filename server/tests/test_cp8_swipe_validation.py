"""Checkpoint 8 — swipe target validation (input-validation coverage).

record_swipe trusted the client-supplied target_id. A swipe must only be recorded
against a profile that is actually a valid deck candidate for the swiper: the opposite
role, visibility 'live', and not the swiper themselves. Otherwise a crafted POST /swipe
could self-match or interact with same-role / hidden / arbitrary profiles.
"""

import uuid

import sqlalchemy as sa

from conftest import login, make_profile, profile_for_email, seed_user_profile


async def _builder(client, db):
    email = f"{uuid.uuid4().hex}@example.com"
    await login(client, email)
    await make_profile(client, role="builder", name="MeBuilder")
    return email, await profile_for_email(db, email)


async def test_cannot_swipe_self(client, db):
    email, me = await _builder(client, db)
    await client.post("/swipe", data={"target_id": str(me.id), "direction": "like"})

    from models import Match, Swipe
    swipes = (await db.execute(sa.select(sa.func.count()).select_from(Swipe)
              .where(Swipe.target_profile_id == me.id))).scalar()
    matches = (await db.execute(sa.select(sa.func.count()).select_from(Match))).scalar()
    assert swipes == 0, "a self-swipe was recorded"
    assert matches == 0, "a self-match was created"


async def test_cannot_swipe_same_role(client, db):
    email, me = await _builder(client, db)
    same_role = await seed_user_profile(db, role="builder", name="OtherBuilder")
    await client.post("/swipe", data={"target_id": str(same_role.id), "direction": "like"})

    from models import Swipe
    cnt = (await db.execute(sa.select(sa.func.count()).select_from(Swipe)
           .where(Swipe.target_profile_id == same_role.id))).scalar()
    assert cnt == 0, "swiped a same-role profile not in the deck"


async def test_cannot_swipe_nonexistent_target(client, db):
    email, me = await _builder(client, db)
    r = await client.post("/swipe", data={"target_id": str(uuid.uuid4()), "direction": "like"})

    from models import Swipe
    cnt = (await db.execute(sa.select(sa.func.count()).select_from(Swipe))).scalar()
    assert cnt == 0
    assert r.status_code in (200, 204, 400, 404)  # must not 500


async def test_cannot_swipe_hidden_profile(client, db):
    email, me = await _builder(client, db)
    hidden = await seed_user_profile(db, role="marketer", name="HiddenMkt")
    # make it non-live
    hidden.visibility = "hidden"
    await db.commit()

    await client.post("/swipe", data={"target_id": str(hidden.id), "direction": "like"})
    from models import Swipe
    cnt = (await db.execute(sa.select(sa.func.count()).select_from(Swipe)
           .where(Swipe.target_profile_id == hidden.id))).scalar()
    assert cnt == 0, "swiped a hidden profile"
