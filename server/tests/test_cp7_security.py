"""Checkpoint 7 — security criteria.

Concrete, automatable security requirements that encode the non-negotiable
basics so the suite itself enforces them.
"""

import uuid


def _all_set_cookies(r) -> str:
    parts = []
    for resp in list(getattr(r, "history", [])) + [r]:
        try:
            parts += resp.headers.get_list("set-cookie")
        except Exception:
            v = resp.headers.get("set-cookie")
            if v:
                parts.append(v)
    return " ".join(parts).lower()


async def test_session_cookie_is_httponly(client):
    """Session cookie must be HttpOnly (not script-readable) — XSS session theft defence."""
    email = f"{uuid.uuid4().hex}@example.com"
    await client.post("/auth/request-link", data={"email": email})
    from conftest import last_magic_link

    path = last_magic_link().split("testserver", 1)[-1]
    token = path.split("token=", 1)[1]
    r = await client.post("/auth/verify", data={"token": token})
    cookies = _all_set_cookies(r)
    assert "httponly" in cookies, f"session cookie not HttpOnly: {cookies[:200]}"


async def test_session_cookie_is_opaque(client):
    """The cookie must not embed PII (email) — it should be an opaque session id."""
    email = f"{uuid.uuid4().hex}@example.com"
    await client.post("/auth/request-link", data={"email": email})
    from conftest import last_magic_link

    path = last_magic_link().split("testserver", 1)[-1]
    token = path.split("token=", 1)[1]
    r = await client.post("/auth/verify", data={"token": token})
    cookies = _all_set_cookies(r)
    local_part = email.split("@")[0]
    assert email not in cookies and local_part not in cookies


async def test_magic_token_is_single_use(client):
    """A magic link must not be replayable after it's been consumed once."""
    email = f"{uuid.uuid4().hex}@example.com"
    await client.post("/auth/request-link", data={"email": email})
    from conftest import last_magic_link

    path = last_magic_link().split("testserver", 1)[-1]
    token = path.split("token=", 1)[1]
    r1 = await client.post("/auth/verify", data={"token": token})
    assert r1.status_code in (200, 302, 303)

    client.cookies.clear()
    r2 = await client.post("/auth/verify", data={"token": token})
    assert r2.status_code in (400, 401, 403), "magic token was replayable"


async def test_mutating_endpoints_require_auth(client):
    """Anonymous POSTs to state-changing endpoints must be rejected."""
    for path, data in (
        ("/swipe", {"target_id": str(uuid.uuid4()), "direction": "like"}),
        ("/connect", {"match_id": str(uuid.uuid4())}),
        ("/intro", {"match_id": str(uuid.uuid4()), "body": "hi"}),
    ):
        r = await client.post(path, data=data)
        assert r.status_code in (302, 303, 401, 403), f"{path} allowed anonymous access"


async def test_discovery_reads_require_auth(client):
    """Login is required to browse profiles — discovery is no longer open to guests."""
    for path in ("/discover", "/deck", "/deck?view=marketer"):
        r = await client.get(path)
        assert r.status_code in (302, 303, 401, 403), \
            f"{path} must require login (guest browsing removed)"
