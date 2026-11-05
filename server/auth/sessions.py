"""Redis-backed session cookies."""

from __future__ import annotations

import secrets
import uuid

from stario import cookies
from stario.http.context import Context
from stario.http.writer import Writer

from auth.redis_client import get_redis
from config import settings

SESSION_COOKIE = "shipswipe_session"
SESSION_TTL = 60 * 60 * 24 * 30  # 30 days

# Mark the cookie Secure on the public HTTPS deployment; stays off for the
# http:// test client so the session round-trips in the suite.
_SECURE_COOKIE = settings.base_url.startswith("https")


def _session_key(session_id: str) -> str:
    """Return the Redis key for a session id."""
    return f"session:{session_id}"


async def create_session(w: Writer, user_id: uuid.UUID) -> str:
    """Persist a new session and set the HttpOnly cookie."""
    session_id = secrets.token_urlsafe(32)
    r = get_redis()
    await r.set(_session_key(session_id), str(user_id), ex=SESSION_TTL)
    cookies.set_cookie(
        w,
        SESSION_COOKIE,
        session_id,
        max_age=SESSION_TTL,
        httponly=True,
        secure=_SECURE_COOKIE,
        samesite="lax",
    )
    return session_id


async def destroy_session(c: Context, w: Writer) -> None:
    """Remove the session from Redis and clear the cookie."""
    session_id = c.req.cookies.get(SESSION_COOKIE)
    if session_id:
        r = get_redis()
        await r.delete(_session_key(session_id))
    cookies.delete_cookie(
        w, SESSION_COOKIE, httponly=True, secure=_SECURE_COOKIE, samesite="lax"
    )


async def session_user_id(c: Context) -> uuid.UUID | None:
    """Return the authenticated user id for this request, if any."""
    session_id = c.req.cookies.get(SESSION_COOKIE)
    if not session_id:
        return None
    r = get_redis()
    raw = await r.get(_session_key(session_id))
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None