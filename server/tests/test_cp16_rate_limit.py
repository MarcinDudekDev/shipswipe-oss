"""Checkpoint 16 — rate-limit /auth/request-link [2026-06-25].

The magic-link endpoint is unauthenticated and sends email, so it must be
throttled per email address: an attacker cannot use it to flood (email-bomb) a
victim's inbox. After a small burst for one email, further requests in the window
are rejected (429) and no further email is queued. Distinct emails are independent.
"""

import uuid


async def test_request_link_is_rate_limited_per_email(client):
    email = f"{uuid.uuid4().hex}@example.com"

    statuses = [
        (await client.post("/auth/request-link", data={"email": email})).status_code
        for _ in range(8)
    ]

    assert statuses[0] == 204, "the first sign-in request must succeed"
    assert 429 in statuses, "repeated requests for one email must be throttled (429)"

    from services.email import OUTBOX

    sent = [m for m in OUTBOX if m["to"] == email]
    assert len(sent) < 8, "throttled requests must not each send an email"


async def test_rate_limit_is_per_email(client):
    # A throttled victim email must not block a different, fresh email.
    victim = f"{uuid.uuid4().hex}@example.com"
    for _ in range(8):
        await client.post("/auth/request-link", data={"email": victim})

    other = f"{uuid.uuid4().hex}@example.com"
    r = await client.post("/auth/request-link", data={"email": other})
    assert r.status_code == 204, "a different email must not be affected by another's limit"
