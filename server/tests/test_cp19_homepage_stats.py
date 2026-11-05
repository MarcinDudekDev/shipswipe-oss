"""Checkpoint 19 — live community stats on the homepage [2026-06-28].

The public landing surfaces real counts so visitors see traction: how many
builders and marketers have registered, and how many matches have been made.
Each stat is rendered with a data-stat marker so the count is gradable.
"""

from conftest import seed_match, seed_user_profile


async def test_homepage_shows_live_counts(client, db):
    b1 = await seed_user_profile(db, role="builder", name="StatB1")
    await seed_user_profile(db, role="builder", name="StatB2")
    m1 = await seed_user_profile(db, role="marketer", name="StatM1")
    await seed_user_profile(db, role="marketer", name="StatM2")
    await seed_user_profile(db, role="marketer", name="StatM3")
    await seed_match(db, b1.id, m1.id)

    r = await client.get("/")
    assert r.status_code == 200
    assert 'data-stat="builders">2<' in r.text, "homepage must show the live builder count"
    assert 'data-stat="marketers">3<' in r.text, "homepage must show the live marketer count"
    assert 'data-stat="matches">1<' in r.text, "homepage must show the live match count"


async def test_homepage_stats_zero_when_empty(client, db):
    # No profiles seeded -> all counts are 0 (honest empty state, still renders).
    r = await client.get("/")
    assert r.status_code == 200
    assert 'data-stat="builders">0<' in r.text
    assert 'data-stat="matches">0<' in r.text
