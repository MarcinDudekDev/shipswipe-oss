"""Security hardening regression tests, part 2 (abuse paths and hostile input).

  - a pass after a match never deletes the match or its messages, and cycling
        pass/like or undo/like cannot re-send match emails or reset the intro throttle.
  - hostile JSON (invalid UTF-8, deep nesting, wrong types, NUL bytes) is a 4xx.
  - profile free-text fields are length-capped before they reach the database.
  - the legal pages show the contact address from settings (CONTACT_EMAIL).
  - POST /auth/verify refuses a cross-site request.
"""

import uuid

import sqlalchemy as sa

from conftest import (
    last_magic_link,
    login,
    make_profile,
    profile_for_email,
    seed_like,
    seed_user_profile,
)


def _email() -> str:
    return f"{uuid.uuid4().hex}@example.com"


def _outbox():
    from services.email import OUTBOX

    return OUTBOX


def _match_mails() -> int:
    return sum(1 for m in _outbox() if "new match" in str(m.get("subject", "")).lower())


async def _count(db, model) -> int:
    return (await db.execute(sa.select(sa.func.count()).select_from(model))).scalar_one()


async def _mutual_match(client, db):
    """Log in as a builder, seed a marketer who already likes us, like back -> match."""
    email = _email()
    await login(client, email)
    await make_profile(client, role="builder", name="Me")
    me_id = (await profile_for_email(db, email)).id
    other_id = (await seed_user_profile(db, "marketer", "Other")).id
    await seed_like(db, other_id, me_id)
    await client.post("/swipe", data={"target_id": str(other_id), "direction": "like"})
    return me_id, other_id


# ---- match lifecycle ----

async def test_pass_after_match_keeps_match_and_messages(client, db):
    from models import Match, Message

    _, other_id = await _mutual_match(client, db)
    assert await _count(db, Match) == 1
    match_id = (await db.execute(sa.select(Match.id))).scalar_one()
    r = await client.post("/intro", data={"match_id": str(match_id), "body": "hello"})
    assert r.status_code < 400
    await client.post("/swipe", data={"target_id": str(other_id), "direction": "pass"})
    db.expire_all()
    assert await _count(db, Match) == 1
    assert await _count(db, Message) == 1


async def test_pass_like_cycling_sends_no_new_match_mail(client, db):
    _, other_id = await _mutual_match(client, db)
    first = _match_mails()
    assert first >= 1
    for _ in range(4):
        await client.post("/swipe", data={"target_id": str(other_id), "direction": "pass"})
        await client.post("/swipe", data={"target_id": str(other_id), "direction": "like"})
    assert _match_mails() == first


async def test_undo_like_cycling_sends_no_new_match_mail(client, db):
    _, other_id = await _mutual_match(client, db)
    first = _match_mails()
    for _ in range(4):
        await client.post("/undo")
        await client.post("/swipe", data={"target_id": str(other_id), "direction": "like"})
    assert _match_mails() == first


async def test_intro_throttle_survives_rematch(client, db):
    from models import Match

    _, other_id = await _mutual_match(client, db)
    for round_ in range(3):
        db.expire_all()
        match_id = (await db.execute(sa.select(Match.id))).scalar_one_or_none()
        if match_id is not None:
            for i in range(6):
                await client.post(
                    "/intro", data={"match_id": str(match_id), "body": f"r{round_} m{i}"}
                )
        await client.post("/undo")
        await client.post("/swipe", data={"target_id": str(other_id), "direction": "like"})
    intro_mails = sum(1 for m in _outbox() if "intro" in str(m.get("subject", "")).lower())
    assert intro_mails <= 5


# ---- hostile input ----

async def test_hostile_json_is_a_client_error(client, db):
    email = _email()
    await login(client, email)
    await make_profile(client)
    json_ct = {"content-type": "application/json"}
    cases = [
        ("/profile", b'{"name": "\xff\xfe"}'),
        ("/swipe", b"[" * 200_000),
        ("/swipe", b'{"target_id": ["x"], "direction": {"a": 1}}'),
        ("/intro", b'{"match_id": 5, "body": null}'),
        ("/auth/request-link", b'{"email": "\xff@example.com"}'),
        ("/auth/verify", b'{"token": 123}'),
    ]
    for path, body in cases:
        r = await client.post(path, content=body, headers=json_ct)
        assert 400 <= r.status_code < 500, (path, body[:40], r.status_code)


async def test_nul_bytes_are_rejected_not_500(client, db):
    email = _email()
    await login(client, email)
    r = await make_profile(client, name="bad\x00name")
    assert 400 <= r.status_code < 500
    r = await client.post(
        "/auth/request-link", data={"email": _email(), "role": "builder", "name": "x\x00y"}
    )
    assert r.status_code < 500


async def test_nul_in_registration_name_does_not_strand_the_token(client):
    email = _email()
    await client.post(
        "/auth/request-link", data={"email": email, "role": "builder", "name": "x\x00y"}
    )
    link = last_magic_link()
    if not link:
        return  # rejected at request time: nothing to strand
    token = link.split("token=", 1)[1]
    r = await client.post("/auth/verify", data={"token": token}, follow_redirects=False)
    assert r.status_code < 500


# ---- length caps ----

async def test_profile_free_text_is_capped(client, db):
    import time

    email = _email()
    await login(client, email)
    await make_profile(client, bio="original")
    for field, value in (
        ("bio", "b" * 100_000),
        ("building", "b" * 10_000),
        ("looking_for", "l" * 10_000),
        ("tags", ",".join(["t" * 30] * 5_000)),
    ):
        started = time.monotonic()
        r = await make_profile(client, **{field: value})
        assert 400 <= r.status_code < 500, field
        assert time.monotonic() - started < 2.0, field
    me = await profile_for_email(db, email)
    await db.refresh(me)
    assert me.bio == "original"


# ---- contact address ----

async def test_legal_pages_use_configured_contact_email(client, monkeypatch):
    import dataclasses

    import config

    patched = dataclasses.replace(config.settings, contact_email="help@example.org")
    monkeypatch.setattr(config, "settings", patched)
    for mod in ("views.legal",):
        import importlib

        m = importlib.import_module(mod)
        if hasattr(m, "settings"):
            monkeypatch.setattr(m, "settings", patched)
    for path in ("/privacy", "/terms"):
        r = await client.get(path)
        assert "help@example.org" in r.text, path


# ---- CSRF on the sign-in POST ----

async def test_cross_site_sign_in_post_is_refused(client):
    for headers in (
        {"origin": "https://evil.example"},
        {"sec-fetch-site": "cross-site"},
    ):
        await client.post("/auth/request-link", data={"email": _email()})
        token = last_magic_link().split("token=", 1)[1]
        r = await client.post(
            "/auth/verify", data={"token": token}, headers=headers, follow_redirects=False
        )
        assert r.status_code == 403, headers
        assert not any("session" in k.lower() for k in client.cookies.keys())


async def test_same_origin_sign_in_post_still_works(client):
    await client.post("/auth/request-link", data={"email": _email()})
    token = last_magic_link().split("token=", 1)[1]
    r = await client.post(
        "/auth/verify",
        data={"token": token},
        headers={"origin": "http://testserver", "sec-fetch-site": "same-origin"},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
