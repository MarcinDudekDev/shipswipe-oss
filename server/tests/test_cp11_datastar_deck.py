"""Checkpoint 11 — Datastar-wired discover deck.

Turns the static server-rendered deck into a live Datastar UI:
  - the page loads the Datastar runtime
  - the deck shows ONE front card at a time (not a stack)
  - Like/Pass buttons POST /swipe (Datastar @post) and the NEXT card is patched
    into #deck over SSE (text/event-stream, event: datastar-patch-elements)
  - the per-card "Details" drawer toggles CLIENT-SIDE (data-show + a signal), no
    server roundtrip
  - a mutual like patches #match-modal into the page over SSE

Stario's TestClient buffers a short-lived SSE handler's full body, so r.text
contains the patch events. /swipe must accept BOTH the existing form transport
(target_id, used by cp4/5/8) AND Datastar's JSON signals body (targetId).
"""

import uuid

import sqlalchemy as sa

from conftest import (
    login, make_profile, profile_for_email, seed_user_profile, seed_like,
)


async def _setup_builder(client, db):
    email = f"{uuid.uuid4().hex}@example.com"
    await login(client, email)
    await make_profile(client, role="builder", name="MeBuilder")
    me = await profile_for_email(db, email)
    return email, me


# ---- page + card wiring -----------------------------------------------------

async def test_discover_loads_datastar_runtime(client, db):
    await _setup_builder(client, db)
    await seed_user_profile(db, role="marketer", name="RuntimeMkt")
    r = await client.get("/discover")
    assert r.status_code == 200
    assert "datastar.js" in r.text or "datastar@" in r.text, \
        "the page must load the Datastar runtime script"


async def test_deck_renders_single_front_card(client, db):
    # three candidates, but only the front one is on screen
    await _setup_builder(client, db)
    await seed_user_profile(db, role="marketer", name="FrontA")
    await seed_user_profile(db, role="marketer", name="FrontB")
    await seed_user_profile(db, role="marketer", name="FrontC")
    r = await client.get("/deck")
    assert r.status_code == 200
    assert r.text.count('data-action="details"') == 1, \
        "deck must show exactly one front card at a time"


async def test_front_card_has_datastar_swipe_controls(client, db):
    _, me = await _setup_builder(client, db)
    target = await seed_user_profile(db, role="marketer", name="SwipeTargetMkt")
    r = await client.get("/deck")
    assert r.status_code == 200
    assert "data-on:click" in r.text, "swipe buttons need a Datastar click handler"
    assert "@post(" in r.text and "/swipe" in r.text, "buttons must @post('/swipe')"
    assert str(target.id) in r.text, "card carries its target id for the swipe"
    # The Datastar expression must be VALID JS: the target id and direction must be
    # QUOTED string literals, not bare tokens. ds.post(payload=...) emits raw JS, so
    # `{'targetId':<uuid>,'direction':like}` is a syntax error that silently breaks
    # the click. Accept either a quoted payload or a quoted signal assignment.
    assert f"'{target.id}'" in r.text, "target id must be a quoted JS string literal"
    assert "'like'" in r.text and "'pass'" in r.text, "directions must be quoted literals"


async def test_front_card_drawer_is_client_reactive(client, db):
    await _setup_builder(client, db)
    await seed_user_profile(db, role="marketer", name="DrawerReactiveMkt")
    r = await client.get("/deck")
    assert r.status_code == 200
    # client-only toggle: a signal + data-show, no @get/@post on the toggle
    assert "data-show" in r.text, "drawer visibility is a reactive data-show"
    assert "detailsOpen" in r.text, "drawer is driven by a detailsOpen signal"


# ---- swipe over SSE ---------------------------------------------------------

async def test_swipe_returns_sse_and_advances(client, db):
    await _setup_builder(client, db)
    a = await seed_user_profile(db, role="marketer", name="GoneAfterSwipe")
    b = await seed_user_profile(db, role="marketer", name="StaysOnDeck")

    r = await client.post("/swipe", data={"target_id": str(a.id), "direction": "pass"})
    assert r.status_code == 200
    assert "text/event-stream" in r.headers.get("content-type", "")
    assert "datastar-patch-elements" in r.text
    assert 'id="deck"' in r.text
    assert "GoneAfterSwipe" not in r.text   # the swiped card is gone
    assert "StaysOnDeck" in r.text          # the next card is patched in


async def test_swipe_accepts_datastar_json_signals(client, db):
    await _setup_builder(client, db)
    target = await seed_user_profile(db, role="marketer", name="JsonSignalMkt")

    # Datastar posts signals as a JSON body (camelCase targetId)
    r = await client.post("/swipe", json={"targetId": str(target.id), "direction": "pass"})
    assert r.status_code == 200
    assert "datastar-patch-elements" in r.text

    from models import Swipe
    cnt = (await db.execute(sa.select(sa.func.count()).select_from(Swipe)
                            .where(Swipe.target_profile_id == target.id))).scalar()
    assert cnt == 1, "swipe must be recorded when sent as Datastar JSON signals"


async def test_swipe_empty_deck_patches_seen_state(client, db):
    await _setup_builder(client, db)
    only = await seed_user_profile(db, role="marketer", name="LastOneMkt")

    r = await client.post("/swipe", data={"target_id": str(only.id), "direction": "pass"})
    assert r.status_code == 200
    assert 'id="deck"' in r.text
    assert r.text.count('data-action="details"') == 0, "no cards left -> no card markup"


async def test_mutual_like_patches_match_modal(client, db):
    email, me = await _setup_builder(client, db)
    other = await seed_user_profile(db, role="marketer", name="MatchModalMkt")
    await seed_like(db, other.id, me.id)  # they liked me first

    r = await client.post("/swipe", data={"target_id": str(other.id), "direction": "like"})
    assert r.status_code == 200
    assert "datastar-patch-elements" in r.text
    assert 'id="match-modal"' in r.text
    assert "MatchModalMkt" in r.text
