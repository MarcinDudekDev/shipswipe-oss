"""Extra hardening coverage — gmail limiter aliases, concurrent signup, 404 headers.

Pins behaviours the main hardening files don't cover: the gmail/googlemail
dot-collapse on the magic-link bucket, the new-user verify race (no 500,
one row), and security headers on unrouted 404s.
"""

import asyncio
import uuid

import sqlalchemy as sa

from conftest import last_magic_link


def _email() -> str:
    return f"{uuid.uuid4().hex}@example.com"


async def test_gmail_dot_and_googlemail_aliases_share_the_link_bucket(client):
    """Gmail dot-variants and googlemail.com fold into one rate-limit bucket."""
    local = uuid.uuid4().hex[:12]
    aliases = [
        f"{local[:4]}.{local[4:8]}.{local[8:]}@gmail.com",
        f"{local[:6]}.{local[6:]}@googlemail.com",
        f"{local}+tag@gmail.com",
        f"{local}@googlemail.com",
        f"{local[:2]}.{local[2:]}@gmail.com",
    ]
    for alias in aliases:
        r = await client.post("/auth/request-link", data={"email": alias})
        assert r.status_code == 204, (alias, r.status_code)
    # Sixth request — the same mailbox by gmail rules — hits the shared bucket.
    r = await client.post("/auth/request-link", data={"email": f"{local}@gmail.com"})
    assert r.status_code == 429


async def test_dot_collapse_leaves_other_providers_alone(client):
    """The fold applies to gmail domains only; other addresses keep literal keys."""
    local = uuid.uuid4().hex[:12]
    for alias in (f"{local[:4]}.{local[4:]}@example.com", f"{local}@example.com"):
        r = await client.post("/auth/request-link", data={"email": alias})
        assert r.status_code == 204, (alias, r.status_code)


async def test_concurrent_verify_same_new_email_no_500(client, db):
    """Two links for one brand-new email consumed at once: one user, no 500."""
    from models import User

    email = _email()
    await client.post("/auth/request-link", data={"email": email})
    token1 = last_magic_link().split("token=", 1)[1]
    await client.post("/auth/request-link", data={"email": email})
    token2 = last_magic_link().split("token=", 1)[1]
    assert token1 != token2

    r1, r2 = await asyncio.gather(
        client.post("/auth/verify", data={"token": token1}, follow_redirects=False),
        client.post("/auth/verify", data={"token": token2}, follow_redirects=False),
    )
    assert r1.status_code != 500
    assert r2.status_code != 500
    assert {r1.status_code, r2.status_code} <= {302, 303}
    users = (
        (await db.execute(sa.select(User).where(User.email == email)))
        .scalars()
        .all()
    )
    assert len(users) == 1


async def test_404_carries_security_headers(client):
    """Unrouted paths skip route middleware — the router's 404 sets headers."""
    r = await client.get("/definitely-not-a-route")
    assert r.status_code == 404
    h = r.headers
    assert h.get("x-content-type-options") == "nosniff"
    assert h.get("referrer-policy") == "strict-origin-when-cross-origin"
    assert h.get("x-frame-options") == "SAMEORIGIN"
