"""Checkpoint 21 — Open Graph / social share image [2026-06-29].

The landing declares OG + Twitter card meta so links unfurl with a real cover,
and the image is served at a stable 200 (a dedicated route, not the fingerprinted
/static redirect, which some scrapers choke on).
"""


async def test_landing_has_og_and_twitter_meta(client):
    r = await client.get("/")
    assert r.status_code == 200
    assert 'property="og:image"' in r.text, "landing must declare an og:image"
    assert "/og-image.png" in r.text, "og:image should point at the served cover"
    assert 'property="og:title"' in r.text
    assert 'property="og:description"' in r.text
    assert 'name="twitter:card"' in r.text and "summary_large_image" in r.text


async def test_og_image_is_served(client):
    r = await client.get("/og-image.png")
    assert r.status_code == 200, "the OG image must be served directly (no redirect)"
    assert "image/png" in r.headers.get("content-type", "")
