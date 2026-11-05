"""Checkpoint 18 — page polish + login from the online E2E audit [2026-06-26].

- Every server-rendered document declares <html lang="en"> (a11y: html-has-lang).
- /matches is a real, styled HTML page (was an unstyled text/plain stub).
- The login gate on member pages renders a friendly sign-in page, not bare text.
- A returning user can LOG IN: GET /login is an email-only magic-link form.
"""

import uuid

from conftest import login, make_profile


async def test_login_page_is_an_email_form(client):
    r = await client.get("/login")
    assert r.status_code == 200
    assert "/auth/request-link" in r.text, "login must post to the magic-link endpoint"
    assert 'type="email"' in r.text or 'name="email"' in r.text, "login needs an email input"


async def test_landing_declares_lang(client):
    r = await client.get("/")
    assert '<html lang="en"' in r.text, "documents must declare lang for accessibility"


async def test_matches_is_a_real_html_page(client, db):
    email = f"{uuid.uuid4().hex}@example.com"
    await login(client, email)
    await make_profile(client, role="builder", name="MatchPager",
                       building="thing", looking_for="partner", terms="rev-share")
    r = await client.get("/matches")
    assert r.status_code == 200
    assert "<html" in r.text.lower() and "/static/styles.css" in r.text, \
        "/matches must be a styled HTML page, not a text/plain stub"
    assert '<html lang="en"' in r.text


async def test_signin_gate_renders_a_page(client):
    # anonymous member page -> a friendly sign-in page (still a non-2xx gate)
    r = await client.get("/discover")
    assert r.status_code in (401, 403)
    assert "<html" in r.text.lower(), "the gate must render a real sign-in page, not bare text"
    assert "/" in r.text  # links back to the landing / sign-in
