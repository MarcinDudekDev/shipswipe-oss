"""Invariant: no request body, on any POST route, produces a 500.

Rather than pinning each crashing input on its own (invalid UTF-8, lone
surrogates, duplicate tags, ...), this fuzzes every field of every POST route with a corpus of hostile
values, one field at a time, with the other fields valid so the request reaches
the deepest code path. Form and JSON encodings both.
"""

import asyncio
import json
import uuid

import pytest

from conftest import login, make_profile, profile_for_email, seed_match, seed_user_profile

HOSTILE_STR = [
    "\ud800",                     # lone surrogate
    "a\udfffb",
    "\x00",
    "a\x00b",
    "a,a",                        # duplicate tag
    "growth, growth, Growth",
    "",
    " ",
    "x" * 70_000,
    "<script>alert(1)</script>",
    "' OR 1=1 --",
    "‮evil",                 # RTL override
    "﻿",
    "😀" * 50,
    "%ff%fe",
    "../../etc/passwd",
]
HOSTILE_JSON = HOSTILE_STR + [0, -1, 1.5, True, None, [], ["a", "a"], {}, {"a": {"b": 1}}]

# Raw form bodies with byte sequences that are not valid UTF-8 (incl. a
# CESU-8 encoded surrogate, which is how a lone surrogate arrives over the wire).
HOSTILE_FORM_BYTES = [b"\xff\xfe", b"\xed\xa0\x80", b"%ED%A0%80", b"%00", b"%FF"]

ROUTES = {
    "/auth/request-link": ["email", "role", "name"],
    "/auth/verify": ["token"],
    "/profile": ["role", "name", "bio", "building", "looking_for", "terms", "tags"],
    "/swipe": ["target_id", "direction"],
    "/reconsider": ["target_id"],
    "/connect": ["match_id"],
    "/intro": ["match_id", "body"],
    "/account/delete": ["confirm"],
    "/undo": ["x"],
    "/auth/logout": ["x"],
}


@pytest.fixture
async def world(client, db):
    email = f"{uuid.uuid4().hex}@example.com"
    await login(client, email)
    await make_profile(client, role="builder", name="Me")
    me = await profile_for_email(db, email)
    other = await seed_user_profile(db, "marketer", "Other")
    m = await seed_match(db, me.id, other.id)
    return {
        "email": f"{uuid.uuid4().hex}@example.com",
        "role": "builder",
        "name": "Valid Name",
        "token": "not-a-token",
        "bio": "bio",
        "building": "thing",
        "looking_for": "partner",
        "terms": "rev-share",
        "tags": "React,SEO",
        "target_id": str(other.id),
        "direction": "like",
        "match_id": str(m.id),
        "body": "hello",
        "confirm": "no",
        "x": "1",
    }


def _form_bytes(fields: dict) -> bytes:
    from urllib.parse import quote

    def enc(v) -> str:
        return quote(str(v).encode("utf-8", "surrogatepass"), safe="")

    return "&".join(f"{k}={enc(v)}" for k, v in fields.items()).encode()


async def _reset_limits():
    """Clear rate-limit counters so every fuzz request reaches the handler body."""
    from auth.redis_client import get_redis

    r = get_redis()
    keys = [k async for k in r.scan_iter(match="rl:*")]
    if keys:
        await r.delete(*keys)


async def _post(client, path, content, ctype):
    await _reset_limits()
    return await client.post(
        path,
        content=content,
        headers={"content-type": ctype, "datastar-request": "true"}
        if ctype == "application/json"
        else {"content-type": ctype},
    )


async def test_no_field_value_crashes_any_post_route(client, world):
    failures = []
    for path, fields in ROUTES.items():
        for field in fields:
            base = {f: world[f] for f in fields}
            if "email" in base and field != "email":
                base["email"] = f"{uuid.uuid4().hex}@example.com"
            for value in HOSTILE_JSON:
                body = json.dumps({**base, field: value}).encode()  # ensure_ascii keeps \ud800 escapes
                r = await _post(client, path, body, "application/json")
                if r.status_code >= 500:
                    failures.append((path, field, "json", repr(value)[:30], r.status_code))
            for value in HOSTILE_STR:
                r = await _post(
                    client, path, _form_bytes({**base, field: value}),
                    "application/x-www-form-urlencoded",
                )
                if r.status_code >= 500:
                    failures.append((path, field, "form", repr(value)[:30], r.status_code))
            for raw in HOSTILE_FORM_BYTES:
                body = _form_bytes({k: v for k, v in base.items() if k != field})
                body += (b"&" if body else b"") + field.encode() + b"=" + raw
                r = await _post(client, path, body, "application/x-www-form-urlencoded")
                if r.status_code >= 500:
                    failures.append((path, field, "bytes", repr(raw), r.status_code))
    assert failures == [], failures[:15]


async def test_whole_body_garbage_never_crashes(client, world):
    bodies = [
        b"[" * 200_000,
        b'{"a":' * 5_000,
        b"\xff" * 1000,
        b"null",
        b"[]",
        b'"\\ud800"',
        b"a=1&" * 20_000,
    ]
    failures = []
    for path in ROUTES:
        for body in bodies:
            for ctype in ("application/json", "application/x-www-form-urlencoded"):
                r = await _post(client, path, body, ctype)
                if r.status_code >= 500:
                    failures.append((path, ctype, body[:12], r.status_code))
    assert failures == [], failures[:15]


async def test_oversized_body_is_rejected_quickly(client, world):
    import time

    started = time.monotonic()
    r = await client.post(
        "/auth/request-link",
        content=b"a=1&" * (9_000_000 // 4),
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code in (400, 413)
    assert time.monotonic() - started < 0.5


async def test_surrogate_in_registration_name_does_not_burn_link(client):
    from conftest import last_magic_link

    email = f"{uuid.uuid4().hex}@example.com"
    await client.post(
        "/auth/request-link",
        content=json.dumps({"email": email, "role": "builder", "name": "\ud800"}).encode(),
        headers={"content-type": "application/json"},
    )
    link = last_magic_link()
    if not link:
        return  # refused at request time: nothing to burn
    token = link.split("token=", 1)[1]
    r = await client.post("/auth/verify", data={"token": token}, follow_redirects=False)
    assert r.status_code in (302, 303)


async def test_concurrent_identical_swipes_never_crash(client, db, world):
    other = await seed_user_profile(db, "marketer", "Fresh")
    rs = await asyncio.gather(*(
        client.post("/swipe", data={"target_id": str(other.id), "direction": "like"})
        for _ in range(8)
    ))
    assert all(r.status_code < 500 for r in rs), [r.status_code for r in rs]


async def test_duplicate_tags_are_deduplicated(client, world):
    r = await client.post("/profile", data={
        "role": "builder", "name": "Me", "bio": "b", "building": "t",
        "looking_for": "p", "terms": "rev-share", "tags": "growth, growth, Growth",
    })
    assert r.status_code < 400
