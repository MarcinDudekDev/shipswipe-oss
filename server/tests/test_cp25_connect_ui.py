"""Checkpoint 25 — Connect + Intro UI wiring on /matches and the match modal.

The endpoints exist since cp6; this pins the user-facing path to them:
  - every match card on GET /matches exposes a [data-action="connect"] control
    carrying that match's id
  - a successful connect reveals #connect-panel with the other profile's
    name/looking_for and an intro composer (textarea name="body" +
    [data-action="send-intro"] posting to /intro)
  - Datastar-flavoured POSTs get SSE patches back (panel/card/modal regions)
  - the match modal patched after a mutual like carries a Connect control
"""

import uuid

from conftest import (
    login, make_profile, profile_for_email, seed_user_profile, seed_like,
    latest_match_id,
)

DS_HEADERS = {"Datastar-Request": "true"}


async def _make_match(client, db):
    """Log in builder A, create a mutual match with marketer B. Returns (a, b, match_id)."""
    email = f"{uuid.uuid4().hex}@example.com"
    await login(client, email)
    await make_profile(client, role="builder", name="PriyaBuilder")
    a = await profile_for_email(db, email)
    b = await seed_user_profile(
        db, role="marketer", name="ConnectUIMkt", looking_for="a builder with traction"
    )
    await seed_like(db, b.id, a.id)
    await client.post("/swipe", data={"target_id": str(b.id), "direction": "like"})
    mid = await latest_match_id(db)
    assert mid is not None
    return a, b, mid


async def test_match_card_has_connect_control(client, db):
    a, b, mid = await _make_match(client, db)
    r = await client.get("/matches")
    assert r.ok
    assert "ConnectUIMkt" in r.text
    assert 'data-action="connect"' in r.text
    assert str(mid) in r.text, "the connect control must carry the match id"


async def test_connect_panel_revealed_after_connect(client, db):
    a, b, mid = await _make_match(client, db)
    r = await client.post("/connect", data={"match_id": str(mid)})
    assert r.ok

    r = await client.get("/matches")
    assert r.ok
    assert 'id="connect-panel"' in r.text
    assert "ConnectUIMkt" in r.text
    assert "a builder with traction" in r.text, "panel must show contact context"
    assert 'name="body"' in r.text, "intro composer field must be named body"
    assert 'data-action="send-intro"' in r.text


async def test_connect_via_datastar_patches_panel_and_card(client, db):
    a, b, mid = await _make_match(client, db)
    r = await client.post("/connect", json={"match_id": str(mid)}, headers=DS_HEADERS)
    assert r.status_code == 200
    assert "datastar-patch-elements" in r.text
    assert 'id="connect-panel"' in r.text
    assert 'data-action="send-intro"' in r.text
    assert f"#match-card-{mid}" in r.text


async def test_intro_via_datastar_confirms_in_status_region(client, db):
    a, b, mid = await _make_match(client, db)
    r = await client.post(
        "/intro",
        json={"match_id": str(mid), "body": "Loved your launch channels — talk?"},
        headers=DS_HEADERS,
    )
    assert r.status_code == 200
    assert 'id="intro-sent"' in r.text
    assert "ConnectUIMkt" in r.text


async def test_empty_intro_via_datastar_shows_rejection(client, db):
    a, b, mid = await _make_match(client, db)
    r = await client.post(
        "/intro", json={"match_id": str(mid), "body": "   "}, headers=DS_HEADERS
    )
    assert 'id="intro-sent"' in r.text

    from models import Message
    import sqlalchemy as sa
    cnt = (await db.execute(sa.select(sa.func.count()).select_from(Message)
                            .where(Message.match_id == mid))).scalar()
    assert cnt == 0


async def test_match_modal_has_connect_control(client, db):
    """The SSE that opens the match modal after a mutual like carries Connect."""
    email = f"{uuid.uuid4().hex}@example.com"
    await login(client, email)
    await make_profile(client, role="builder", name="ModalBuilder")
    a = await profile_for_email(db, email)
    b = await seed_user_profile(db, role="marketer", name="ModalMkt")
    await seed_like(db, b.id, a.id)

    r = await client.post("/swipe", data={"target_id": str(b.id), "direction": "like"})
    assert r.status_code == 200
    assert 'id="match-modal"' in r.text
    assert 'data-action="connect"' in r.text


async def test_no_matches_keeps_empty_state(client, db):
    email = f"{uuid.uuid4().hex}@example.com"
    await login(client, email)
    await make_profile(client, role="builder", name="NoMatchBuilder")
    r = await client.get("/matches")
    assert r.ok
    assert "No matches yet" in r.text
    assert 'data-action="connect"' not in r.text
