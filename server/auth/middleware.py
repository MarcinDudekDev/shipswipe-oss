"""Request middleware: user loading + baseline response security headers."""

from __future__ import annotations

from urllib.parse import urlparse

from stario import responses
from stario.http.context import Context, Handler, Writer

from auth.redis_client import get_redis
from auth.sessions import SESSION_COOKIE, session_user_id
from config import settings
from db import async_session
from models import User


def set_baseline_headers(w: Writer) -> None:
    """Write the nosniff/referrer/frame headers every response should carry."""
    w.headers.rset(b"x-content-type-options", b"nosniff")
    w.headers.rset(b"referrer-policy", b"strict-origin-when-cross-origin")
    w.headers.rset(b"x-frame-options", b"SAMEORIGIN")


def security_headers(handler: Handler) -> Handler:
    """Baseline response headers; member pages and the GDPR export go no-store.

    Runs inside ``load_user`` (pushed before it), so ``c.state['user']`` is
    already populated. Headers must be set before the handler writes —
    Stario finalizes them at first write.
    """

    async def wrapper(c: Context, w: Writer) -> None:
        """Set the baseline headers before the handler writes."""
        set_baseline_headers(w)
        if c.state.get("user") is not None or c.req.path == "/account/export":
            w.headers.rset(b"cache-control", b"private, no-store")
        await handler(c, w)

    return wrapper


def _normalized_port(parsed) -> int | None:
    """An explicit default port counts as no port (:443 on https, :80 on http)."""
    port = parsed.port
    scheme = (parsed.scheme or "").lower()
    if (scheme, port) in (("https", 443), ("http", 80)):
        return None
    return port


def _cross_site(c: Context) -> bool:
    """True when the request demonstrably came from another site.

    Sec-Fetch-Site anything but same-origin/none, or an Origin that doesn't
    match BASE_URL's scheme+host+port, means cross-site. Requests carrying
    neither header are let through (curl, some browsers, same-origin fetches
    may omit both). BASE_URL is the public origin — the Host header can't be
    trusted here because a proxy may rewrite it.
    """
    fetch_site = c.req.headers.get("sec-fetch-site")
    if fetch_site is not None:
        # Browser-computed and unforgeable by cross-site JS: trust a
        # same-origin/none assertion outright, refuse anything else.
        return fetch_site.strip().lower() not in ("same-origin", "none")
    origin = c.req.headers.get("origin")
    if origin is None:
        return False
    try:
        parsed = urlparse(origin)
        base = urlparse(settings.base_url)
        ports = (_normalized_port(parsed), _normalized_port(base))
    except ValueError:
        return True
    if not parsed.hostname or not base.hostname:
        return True
    return (
        (parsed.scheme or "").lower() != (base.scheme or "").lower()
        or parsed.hostname.lower() != base.hostname.lower()
        or ports[0] != ports[1]
    )


def origin_check(handler: Handler) -> Handler:
    """Refuse cross-site POSTs before any handler writes state.

    Every mutating route gets what used to be only the sign-in check:
    a demonstrably cross-site POST is a 403 with no write — a sibling
    subdomain otherwise rides the SameSite=Lax session cookie through.
    Runs inside ``security_headers`` so the refusal still carries the
    baseline headers.
    """

    async def wrapper(c: Context, w: Writer) -> None:
        """403 a cross-site POST; pass everything else through."""
        if c.req.method == "POST" and _cross_site(c):
            responses.text(w, "Forbidden.", status=403)
            return
        await handler(c, w)

    return wrapper


def load_user(handler: Handler) -> Handler:
    """Attach ``c.state['user']`` when a valid session cookie is present."""

    async def wrapper(c: Context, w: Writer) -> None:
        """Load the session user into c.state, dropping banned sessions."""
        user_id = await session_user_id(c)
        if user_id is not None:
            async with async_session() as db:
                user = await db.get(User, user_id)
            if user is not None and user.status == "active":
                c.state["user"] = user
            elif user is not None:
                # Non-active (e.g. banned): kill the session so the request
                # proceeds anonymous instead of serving a dead account.
                session_id = c.req.cookies.get(SESSION_COOKIE)
                if session_id:
                    await get_redis().delete(f"session:{session_id}")
        await handler(c, w)

    return wrapper