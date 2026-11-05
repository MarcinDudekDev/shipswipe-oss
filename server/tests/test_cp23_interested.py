"""Checkpoint 23 — the Interested (pending) list + interest-sent toast.

Early-user confusion (2026-06-30): after reconsidering a profile and tapping
Interested, the person vanished — not in the deck, not rejected, not matched
(no reciprocal interest yet), with no feedback. Mutual gating is intentional, so
the fix is feedback: a confirmation toast + an "Interested" list of pending likes.

GET  /interested  -> profiles I liked that haven't matched yet (awaiting response)
POST /swipe like  -> when it doesn't match, the SSE response carries a #toast
"""

import uuid

from conftest import login, make_profile, profile_for_email, seed_user_profile, seed_like


async def _setup_builder(client, db):
    email = f"{uuid.uuid4().hex}@example.com"
    await login(client, email)
    await make_profile(client, role="builder", name="MeBuilder")
    return email, await profile_for_email(db, email)


async def test_interested_lists_liked_not_matched(client, db):
    await _setup_builder(client, db)
    t = await seed_user_profile(db, role="marketer", name="PendingMkt")

    await client.post("/swipe", data={"target_id": str(t.id), "direction": "like"})

    r = await client.get("/interested")
    assert r.ok
    assert "PendingMkt" in r.text
    assert "Awaiting response" in r.text


async def test_interested_excludes_matched(client, db):
    _, me = await _setup_builder(client, db)
    t = await seed_user_profile(db, role="marketer", name="MutualMkt")
    await seed_like(db, t.id, me.id)  # they already like me -> my like makes a match

    await client.post("/swipe", data={"target_id": str(t.id), "direction": "like"})

    interested = (await client.get("/interested")).text
    matches = (await client.get("/matches")).text
    assert "MutualMkt" not in interested  # moved to matches, not pending
    assert "MutualMkt" in matches


async def test_interested_excludes_rejected(client, db):
    await _setup_builder(client, db)
    t = await seed_user_profile(db, role="marketer", name="PassedMkt")

    await client.post("/swipe", data={"target_id": str(t.id), "direction": "pass"})

    assert "PassedMkt" not in (await client.get("/interested")).text


async def test_like_without_match_returns_toast(client, db):
    await _setup_builder(client, db)
    t = await seed_user_profile(db, role="marketer", name="ToastMkt")

    r = await client.post("/swipe", data={"target_id": str(t.id), "direction": "like"})
    assert r.ok
    assert "Interest sent" in r.text
    assert "ToastMkt" in r.text
    assert "toast" in r.text


async def test_pass_does_not_toast(client, db):
    await _setup_builder(client, db)
    t = await seed_user_profile(db, role="marketer", name="QuietPass")

    r = await client.post("/swipe", data={"target_id": str(t.id), "direction": "pass"})
    assert r.ok
    assert "Interest sent" not in r.text


async def test_match_shows_modal_not_toast(client, db):
    _, me = await _setup_builder(client, db)
    t = await seed_user_profile(db, role="marketer", name="ModalMkt")
    await seed_like(db, t.id, me.id)

    r = await client.post("/swipe", data={"target_id": str(t.id), "direction": "like"})
    assert r.ok
    assert "connection" in r.text  # match modal copy
    assert "Interest sent" not in r.text


async def test_interested_requires_login(client, db):
    r = await client.get("/interested")
    assert r.status_code in (302, 303, 401, 403)
