"""Checkpoint 17 — profile completion screen after login [2026-06-26].

Registration only captures side + name, so a fresh user's profile is incomplete
(no building / looking-for / terms). After login they must land on an editable
profile screen to finish it, then flow on to the deck:

  GET  /profile (authed)  -> a real HTML <form> posting to /profile, with fields
                             for name, building, looking_for, terms, bio (+ role).
  verify, incomplete profile -> redirect to /profile (the completion screen)
  verify, complete profile   -> redirect to /discover
  POST /profile (save)       -> redirect onward to /discover
"""

import uuid

from conftest import last_magic_link, login, make_profile


def _verify_path(link: str) -> str:
    return link.split("testserver", 1)[-1] if "testserver" in link else link


async def test_profile_page_is_an_editable_form(client):
    email = f"{uuid.uuid4().hex}@example.com"
    await login(client, email)
    r = await client.get("/profile")
    assert r.status_code == 200
    assert "/profile" in r.text and "form" in r.text.lower(), "profile must be an HTML form"
    for field in ("name", "building", "looking_for", "terms", "bio"):
        assert f'name="{field}"' in r.text, f"profile form needs a {field} field"


async def test_login_sends_incomplete_profile_to_completion(client):
    email = f"{uuid.uuid4().hex}@example.com"
    # register (side + name only) -> profile exists but is incomplete
    await client.post("/auth/request-link", json={"email": email, "role": "builder", "name": "Newbie"})
    # the client follows the post-login redirect; incomplete -> the editable form
    path = _verify_path(last_magic_link())
    r = await client.post("/auth/verify", data={"token": path.split("token=", 1)[1]})
    assert r.status_code == 200
    assert 'action="/profile"' in r.text and 'name="building"' in r.text, \
        "an incomplete profile must land on the completion screen"


async def test_login_with_complete_profile_goes_to_discover(client):
    email = f"{uuid.uuid4().hex}@example.com"
    await login(client, email)
    await make_profile(client, role="builder", name="Done",
                       building="B2B invoicing", looking_for="a growth partner",
                       terms="rev-share")
    # log in again — now the profile is complete -> straight to the deck
    await client.post("/auth/request-link", data={"email": email})
    path = _verify_path(last_magic_link())
    r = await client.post("/auth/verify", data={"token": path.split("token=", 1)[1]})
    assert r.status_code == 200
    assert 'id="deck"' in r.text, "a complete profile should land on the deck"
    assert 'action="/profile"' not in r.text, "a complete profile must not be sent back to the form"


async def test_saving_profile_redirects_to_discover(client):
    email = f"{uuid.uuid4().hex}@example.com"
    await login(client, email)
    r = await make_profile(client, role="builder", name="Saver",
                           building="thing", looking_for="partner", terms="equity")
    assert r.status_code in (303, 200), "saving the profile should succeed"
