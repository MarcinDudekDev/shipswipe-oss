"""Magic-link token issue and verification."""

from __future__ import annotations

import secrets

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from auth.redis_client import get_redis
from config import settings

_TOKEN_TTL = 900  # 15 minutes
_serializer = URLSafeTimedSerializer(settings.magic_link_secret, salt="magic-link")


def _nonce_key(nonce: str) -> str:
    """Return the Redis key for a magic-link nonce."""
    return f"magic:{nonce}"


async def issue_magic_link(email: str) -> str:
    """Create a signed single-use token and store its nonce in Redis."""
    nonce = secrets.token_urlsafe(16)
    r = get_redis()
    await r.set(_nonce_key(nonce), email.lower(), ex=_TOKEN_TTL)
    return _serializer.dumps({"email": email.lower(), "nonce": nonce})


def peek_magic_token(token: str) -> str | None:
    """Signature + expiry check without touching the nonce (GET confirm page)."""
    try:
        data = _serializer.loads(token, max_age=_TOKEN_TTL)
    except (BadSignature, SignatureExpired):
        return None
    email = data.get("email")
    return email if email and data.get("nonce") else None


async def consume_magic_token(token: str) -> str | None:
    """Validate token signature, expiry, and single-use nonce. Returns email or None."""
    try:
        data = _serializer.loads(token, max_age=_TOKEN_TTL)
    except (BadSignature, SignatureExpired):
        return None

    email = data.get("email")
    nonce = data.get("nonce")
    if not email or not nonce:
        return None

    # GETDEL consumes the nonce atomically: two concurrent verifies can't both
    # pass a get-then-delete check and mint two sessions from one link.
    r = get_redis()
    stored = await r.getdel(_nonce_key(nonce))
    if stored is None or stored != email:
        return None

    return email