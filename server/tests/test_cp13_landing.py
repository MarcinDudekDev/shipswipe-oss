"""Checkpoint 13 — real server-rendered landing at GET / [2026-06-25].

The root page is the public front door. With guest browsing removed (cp9 reversed),
a visitor must be able to sign in straight from the landing. So GET / must be a real
marketing landing — NOT the dev scaffold — and must carry the inline magic-link
sign-in form (posts the visitor's email to /auth/request-link) plus the shared
stylesheet so it looks like the rest of the app.
"""


async def test_root_is_real_landing_not_scaffold(client):
    r = await client.get("/")
    assert r.status_code == 200
    assert "backend is running" not in r.text.lower(), \
        "root must be a real landing, not the dev scaffold"


async def test_landing_explains_value_prop(client):
    r = await client.get("/")
    assert r.status_code == 200
    text = r.text.lower()
    assert "builder" in text and "marketer" in text, \
        "landing must explain the builder<->marketer matching value prop"


async def test_landing_has_inline_magic_link_form(client):
    r = await client.get("/")
    assert r.status_code == 200
    assert "/auth/request-link" in r.text, \
        "landing must wire the inline sign-in form to /auth/request-link"
    assert 'type="email"' in r.text or 'name="email"' in r.text, \
        "the sign-in form needs an email input"


async def test_landing_loads_shared_stylesheet(client):
    r = await client.get("/")
    assert r.status_code == 200
    assert "/static/styles.css" in r.text, "landing must load the shared stylesheet"


async def test_landing_links_favicon(client):
    r = await client.get("/")
    assert r.status_code == 200
    assert 'rel="icon"' in r.text and "favicon" in r.text, \
        "landing must link a favicon so the browser tab shows a brand icon"


async def test_favicon_served_at_root(client):
    """Browsers probe /favicon.ico directly — it must not 404."""
    r = await client.get("/favicon.ico")
    assert r.status_code in (200, 301, 302, 307, 308), "/favicon.ico must resolve, not 404"
