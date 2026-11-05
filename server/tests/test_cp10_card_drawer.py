"""Checkpoint 10 — compact deck card with a details drawer.

Friend feedback (2026-06-25): keep the essential profile info on the card front;
tuck the secondary details behind a single button (a drawer) in the corner. The
server-rendered deck card must therefore:

  - expose a single details affordance (reuse the demo hook: data-action="details")
  - show the headline matching info (name + looking_for) on the card front
  - still carry the secondary fields (building/channels, terms) in the markup so the
    drawer can present them without a client-side roster

Discovery is login-gated, so we sign in as a builder first; the seeded marketer is
then the opposite-role candidate on the deck.
"""

import uuid

from conftest import login, make_profile, seed_user_profile


async def _seed_and_get_deck(client, db):
    await seed_user_profile(
        db, role="marketer", name="DrawerMkt",
        terms="rev-share", building="Content SEO and paid social",
        looking_for="a technical founder with a shipped product",
    )
    await login(client, f"{uuid.uuid4().hex}@example.com")
    await make_profile(client, role="builder", name="MeBuilder")
    r = await client.get("/deck")
    assert r.status_code == 200
    return r.text


async def test_card_has_single_details_affordance(client, db):
    text = await _seed_and_get_deck(client, db)
    assert 'data-action="details"' in text, "card needs one details/drawer button"


async def test_card_front_shows_name_and_looking_for(client, db):
    text = await _seed_and_get_deck(client, db)
    assert "DrawerMkt" in text
    assert "technical founder" in text


async def test_card_carries_secondary_fields_for_drawer(client, db):
    text = await _seed_and_get_deck(client, db)
    assert "Content SEO and paid social" in text  # building/channels -> drawer
    assert "rev-share" in text.lower()             # terms -> drawer
