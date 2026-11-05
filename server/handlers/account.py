"""GDPR self-serve handlers: full data export and account deletion."""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import sqlalchemy as sa
from stario import responses
from stario.http.context import Context
from stario.http.writer import Writer

from auth.gate import current_user, reject_anonymous
from auth.sessions import destroy_session
from db import async_session
from models import Match, Message, Profile, ProfileTag, Swipe, User
from services.forms import parse_form
from services.profile import get_profile_for_user


def _iso(dt: datetime | None) -> str | None:
    """Format a datetime as ISO 8601, or None."""
    return dt.isoformat() if dt is not None else None


async def account_export(c: Context, w: Writer) -> None:
    """Everything we hold about the signed-in user, as a JSON download.

    Includes their own data only — a match lists the partner's display name and
    profile id (both already visible in-app), never their email.
    """
    if reject_anonymous(c, w):
        return

    user = current_user(c)
    if user is None:
        responses.text(w, "Unauthorized", status=401)
        return

    payload: dict = {
        "user": {
            "id": str(user.id),
            "email": user.email,
            "email_verified_at": _iso(user.email_verified_at),
            "created_at": _iso(user.created_at),
            "last_seen_at": _iso(user.last_seen_at),
        },
        "profile": None,
        "tags": [],
        "swipes": [],
        "matches": [],
        "messages": [],
    }

    async with async_session() as db:
        profile = await get_profile_for_user(db, user.id)
        if profile is not None:
            pid = profile.id
            payload["profile"] = {
                "role": profile.role,
                "name": profile.name,
                "label": profile.label,
                "bio": profile.bio,
                "building": profile.building,
                "looking_for": profile.looking_for,
                "terms": profile.terms,
                "visibility": profile.visibility,
            }
            payload["tags"] = list(
                (
                    await db.execute(
                        sa.select(ProfileTag.tag).where(ProfileTag.profile_id == pid)
                    )
                ).scalars()
            )
            payload["swipes"] = [
                {
                    "target_profile_id": str(s.target_profile_id),
                    "direction": s.direction,
                    "created_at": _iso(s.created_at),
                }
                for s in (
                    await db.execute(
                        sa.select(Swipe).where(Swipe.swiper_profile_id == pid)
                    )
                ).scalars()
            ]

            matches = (
                await db.execute(
                    sa.select(Match).where(
                        sa.or_(
                            Match.profile_a_id == pid,
                            Match.profile_b_id == pid,
                        )
                    )
                )
            ).scalars().all()
            partner_ids = [
                m.profile_b_id if m.profile_a_id == pid else m.profile_a_id
                for m in matches
            ]
            partners = {}
            if partner_ids:
                partners = {
                    p.id: p
                    for p in (
                        await db.execute(
                            sa.select(Profile).where(Profile.id.in_(partner_ids))
                        )
                    ).scalars()
                }
            payload["matches"] = [
                {
                    "id": str(m.id),
                    "created_at": _iso(m.created_at),
                    "connected_at": _iso(m.connected_at),
                    "partner": (
                        {"profile_id": str(partner.id), "name": partner.name}
                        if (partner := partners.get(other_id)) is not None
                        else None
                    ),
                }
                for m, other_id in zip(matches, partner_ids)
            ]

            payload["messages"] = [
                {
                    "match_id": str(m.match_id),
                    "body": m.body,
                    "created_at": _iso(m.created_at),
                    "read_at": _iso(m.read_at),
                }
                for m in (
                    await db.execute(
                        sa.select(Message).where(Message.sender_profile_id == pid)
                    )
                ).scalars()
            ]

    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    w.headers.rset(
        b"content-disposition", b'attachment; filename="shipswipe-data-export.json"'
    )
    w.respond(body, b"application/json; charset=utf-8", 200)


async def account_delete(c: Context, w: Writer) -> None:
    """Permanently delete the account and every row it owns.

    App-level deletes in FK order (messages -> matches -> swipes -> tags ->
    profile -> user) so no migration or ON DELETE CASCADE is needed. Swipes and
    matches that merely *reference* the profile (other members' swipes on them)
    go too — leaving them would orphan the FK once the profile row is gone.
    """
    if reject_anonymous(c, w):
        return

    user = current_user(c)
    if user is None:
        responses.text(w, "Unauthorized", status=401)
        return

    form = await parse_form(c)
    if form.get("confirm") != "DELETE":
        responses.text(w, 'Type DELETE to confirm account deletion.', status=400)
        return

    user_id = user.id
    async with async_session() as db:
        # Lock the whole row graph top-down — user, then profile, then the
        # member's match rows — in the same order every other writer takes
        # those rows (a profile save pins the user via its foreign key
        # before touching the profile row; a swipe pins both profiles; an
        # intro pins its sender profile before the match). A request racing
        # this delete then blocks until it commits and afterwards finds the
        # rows gone or fails its own FK check — instead of the two
        # transactions deadlocking on opposite lock orders, or this delete
        # tripping a constraint on a row inserted mid-way.
        await db.execute(
            sa.select(User.id).where(User.id == user_id).with_for_update()
        )
        profile = (
            await db.execute(
                sa.select(Profile)
                .where(Profile.user_id == user_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if profile is not None:
            pid: uuid.UUID = profile.id
            member_matches = sa.select(Match.id).where(
                sa.or_(Match.profile_a_id == pid, Match.profile_b_id == pid)
            )
            # Lock the match rows before deleting under them: an in-flight
            # intro locks the same row, so it either commits its message
            # before this delete runs or finds the match already gone —
            # never an FK violation mid-delete.
            await db.execute(member_matches.with_for_update())
            await db.execute(
                sa.delete(Message).where(
                    sa.or_(
                        Message.match_id.in_(member_matches),
                        Message.sender_profile_id == pid,
                    )
                )
            )
            await db.execute(
                sa.delete(Match).where(
                    sa.or_(Match.profile_a_id == pid, Match.profile_b_id == pid)
                )
            )
            await db.execute(
                sa.delete(Swipe).where(
                    sa.or_(
                        Swipe.swiper_profile_id == pid,
                        Swipe.target_profile_id == pid,
                    )
                )
            )
            await db.execute(
                sa.delete(ProfileTag).where(ProfileTag.profile_id == pid)
            )
            await db.execute(sa.delete(Profile).where(Profile.id == pid))
        await db.execute(sa.delete(User).where(User.id == user_id))
        await db.commit()

    # Kill the Redis session + cookie — the account no longer exists.
    await destroy_session(c, w)
    responses.redirect(w, "/", status=303)
