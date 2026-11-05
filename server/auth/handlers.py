"""Auth and profile HTTP handlers."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import sqlalchemy as sa
from stario import responses
from stario.http.context import Context
from stario.http.writer import Writer

from auth.emails import limiter_key, normalize_email
from auth.ratelimit import rate_limited
from auth.redis_client import get_redis
from auth.sessions import create_session, destroy_session
from auth.tokens import consume_magic_token, issue_magic_link, peek_magic_token
from config import settings
from db import async_session
from models import User
from services import email as email_service
from services.forms import clean_field, parse_form
from services.profile import (
    get_profile_for_user,
    profile_is_complete,
    upsert_profile,
)

_VALID_ROLES = {"builder", "marketer"}

# Anti email-bomb throttle on the unauthenticated magic-link endpoint.
_RL_EMAIL_MAX = 5
_RL_EMAIL_WINDOW = 900  # 15 minutes
_RL_IP_MAX = 30
_RL_IP_WINDOW = 3600  # 1 hour


def _reg_key(email: str) -> str:
    """Return the Redis key under which pending registration data is stashed."""
    return f"reg:{email.lower()}"


async def request_link(c: Context, w: Writer) -> None:
    """POST /auth/request-link — validate the email, throttle, then issue a magic link."""
    fields = await parse_form(c)
    email = normalize_email(fields.get("email"))
    if email is None:
        responses.text(w, "Enter a valid email address.", status=400)
        return

    # Landing registration: the chosen side + name ride along to verify.
    # parse_form already dropped any field that can't survive UTF-8/NUL
    # checks, so a name or role here is a clean string; an unknown role or
    # an overlong name simply skips the stash — the link still signs in.
    role = fields.get("role", "").strip().lower()
    name = fields.get("name", "").strip()

    # Throttle per email (always) and per client IP when Cloudflare reports one.
    # The origin must only be reachable through the Cloudflare tunnel — anything
    # else lets a caller spoof or drop cf-connecting-ip and escape the bucket.
    ip = c.req.headers.get("cf-connecting-ip", "")
    if await rate_limited(
        f"rl:link:{limiter_key(email)}", _RL_EMAIL_MAX, _RL_EMAIL_WINDOW
    ) or (
        ip and await rate_limited(f"rl:linkip:{ip}", _RL_IP_MAX, _RL_IP_WINDOW)
    ):
        responses.text(w, "Too many sign-in requests. Try again later.", status=429)
        return

    token = await issue_magic_link(email)

    # Stash the registration so verify can build the profile. Email-only
    # logins skip this (no profile fabricated).
    if role in _VALID_ROLES and name and len(name) <= 255:
        await get_redis().set(
            _reg_key(email), json.dumps({"role": role, "name": name}), ex=900
        )

    link = f"{settings.base_url.rstrip('/')}/auth/verify?token={token}"
    await email_service.send_async(
        to=email,
        subject="Your ShipSwipe login link",
        body=f"Click to sign in: {link}",
        link=link,
    )
    responses.empty(w, status=204)


async def _consume_registration(email: str) -> dict[str, str] | None:
    """Pop the stashed registration payload for this email, atomically."""
    r = get_redis()
    raw = await r.getdel(_reg_key(email))
    if raw is None:
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    # A malformed or unusable payload means "no registration": verify still
    # signs the member in — it just skips creating the profile. The fields
    # get the same sanitising pass as a request body so a poisoned stash can
    # never take verify down after the nonce is consumed.
    if not isinstance(data, dict):
        return None
    role, name = data.get("role"), clean_field(data.get("name"))
    if role not in _VALID_ROLES or not name or len(name) > 255:
        return None
    return {"role": role, "name": name}


async def verify(c: Context, w: Writer) -> None:
    """GET the magic link: confirm only — the session is created by POST.

    Mail scanners prefetch GET links, so the token must survive the landing;
    signing in is a form POST that a scanner never makes.
    """
    token = clean_field(c.req.query.get("token"))
    email = peek_magic_token(token) if token else None
    if email is None:
        responses.text(w, "Invalid or expired link.", status=401)
        return

    from views.login import render_verify_confirm_page  # lazy: avoid import cycle

    responses.html(w, render_verify_confirm_page(email=email, token=token))


async def verify_post(c: Context, w: Writer) -> None:
    """Consume the token, create the session, and land on the app."""
    fields = await parse_form(c)
    token = fields.get("token")
    if not token:
        responses.text(w, "Invalid or expired link.", status=401)
        return

    email = await consume_magic_token(token)
    if not email:
        responses.text(w, "Invalid or expired link.", status=401)
        return

    now = datetime.now(timezone.utc)
    async with async_session() as db:
        result = await db.execute(sa.select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user is not None and user.status != "active":
            responses.text(w, "This account is not active.", status=403)
            return
        if user is None:
            user = User(email=email, email_verified_at=now)
            db.add(user)
            try:
                await db.commit()
            except sa.exc.IntegrityError:
                # Two links for a brand-new email can be consumed at once:
                # by the time the unique violation surfaces, the winner's
                # row is committed — roll back and pick it up instead of 500.
                await db.rollback()
                result = await db.execute(
                    sa.select(User).where(User.email == email)
                )
                user = result.scalar_one_or_none()
                if user is None or user.status != "active":
                    responses.text(w, "This account is not active.", status=403)
                    return
        else:
            user.email_verified_at = now
            await db.commit()
        await db.refresh(user)
        user_id = user.id

    # If they registered from the landing (role + name stashed), create their
    # bare profile now (they'll finish it on the completion screen).
    registration = await _consume_registration(email)
    async with async_session() as db:
        profile = await get_profile_for_user(db, user_id)
        if profile is None and registration is not None:
            profile = await upsert_profile(
                db, user,
                role=registration["role"], name=registration["name"],
                bio="", building="", looking_for="", terms="flexible", tags="",
            )

    await create_session(w, user_id)
    # Finish the profile before swiping; complete profiles go straight to the deck.
    destination = "/discover" if profile_is_complete(profile) else "/profile"
    responses.redirect(w, destination, status=303)


async def logout(c: Context, w: Writer) -> None:
    """POST /auth/logout — destroy the session and clear its cookie."""
    await destroy_session(c, w)
    responses.empty(w, status=204)


