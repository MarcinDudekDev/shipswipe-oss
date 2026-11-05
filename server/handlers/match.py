"""Matches, connect, and intro handlers."""

from __future__ import annotations

import uuid

from stario import datastar as ds
from stario import responses
from stario.http.context import Context
from stario.http.writer import Writer

from auth.gate import current_user, reject_anonymous, require_user_page
from auth.ratelimit import rate_limited
from db import async_session
from models import Match, Profile
from services.forms import parse_form, safe_signals, str_field
from services.matching import (
    connect_match,
    get_match_for_profile,
    get_other_profile,
    list_interested,
    list_matches,
    list_rejected,
    reconsider_swipe,
    send_intro,
)
from services.profile import get_profile_for_user, lock_profile
from views.deck import render_connected_modal
from views.interested import render_interested_page
from views.matches import (
    render_connect_panel,
    render_intro_status,
    render_match_card,
    render_matches_page,
)
from views.rejected import render_rejected_list, render_rejected_page


async def _require_profile(c: Context, w: Writer):
    """Return the caller's profile, writing a 403 when it doesn't exist."""
    user = current_user(c)
    if user is None:
        return None
    async with async_session() as db:
        profile = await get_profile_for_user(db, user.id)
    if profile is None:
        responses.text(w, "Create a profile first.", status=403)
        return None
    return profile


async def matches(c: Context, w: Writer) -> None:
    """GET /matches — list the member's mutual matches."""
    if require_user_page(c, w):
        return

    profile = await _require_profile(c, w)
    if profile is None:
        return

    async with async_session() as db:
        rows = await list_matches(db, profile)

    responses.html(w, render_matches_page(rows))


async def interested(c: Context, w: Writer) -> None:
    """GET /interested — list likes not yet reciprocated."""
    if require_user_page(c, w):
        return

    profile = await _require_profile(c, w)
    if profile is None:
        return

    async with async_session() as db:
        rows = await list_interested(db, profile)

    responses.html(w, render_interested_page(rows))


async def rejected(c: Context, w: Writer) -> None:
    """GET /rejected — list passed profiles that can be reconsidered."""
    if require_user_page(c, w):
        return

    profile = await _require_profile(c, w)
    if profile is None:
        return

    async with async_session() as db:
        rows = await list_rejected(db, profile)

    responses.html(w, render_rejected_page(rows))


async def reconsider(c: Context, w: Writer) -> None:
    """POST /reconsider — return a passed profile to the deck."""
    if reject_anonymous(c, w):
        return

    profile = await _require_profile(c, w)
    if profile is None:
        return

    raw_target = str_field(await parse_form(c), "target_id", "targetId")
    if not raw_target:
        raw_target = str_field(await safe_signals(c), "target_id", "targetId")

    try:
        target_id = uuid.UUID(raw_target)
    except ValueError:
        responses.text(w, "Invalid target.", status=400)
        return

    async with async_session() as db:
        await reconsider_swipe(db, profile, target_id)
        rows = await list_rejected(db, profile)

    ds.sse.patch_elements(
        w,
        render_rejected_list(rows),
        mode="outer",
        selector="#rejected-list",
    )


def _is_datastar(c: Context) -> bool:
    """True when the request came from a Datastar fetch action (@post & co.)."""
    return c.req.headers.get("datastar-request") is not None


async def _match_id_from_request(c: Context) -> uuid.UUID | None:
    """match_id arrives as a form field or inside Datastar's JSON body."""
    raw = str_field(await parse_form(c), "match_id", "matchId")
    if not raw:
        raw = str_field(await safe_signals(c), "match_id", "matchId")
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


async def connect(c: Context, w: Writer) -> None:
    """POST /connect — mark a match as connected and patch the panel."""
    if reject_anonymous(c, w):
        return

    profile = await _require_profile(c, w)
    if profile is None:
        return

    match_id = await _match_id_from_request(c)
    if match_id is None:
        responses.text(w, "Invalid match.", status=400)
        return

    async with async_session() as db:
        match = await get_match_for_profile(db, match_id, profile)
        if match is None:
            responses.text(w, "Match not found.", status=404)
            return
        await connect_match(db, match)
        other = await get_other_profile(db, match, profile)

    if not _is_datastar(c) or other is None:
        responses.text(w, "Connected")
        return

    # Patch every region the connect affects; pages simply drop selectors they
    # don't have (#connect-panel lives on /matches, #match-modal on /discover).
    ds.sse.patch_elements(
        w,
        render_connect_panel(match, other),
        mode="outer",
        selector="#connect-panel",
    )
    ds.sse.patch_elements(
        w,
        render_match_card(match, other),
        mode="outer",
        selector=f"#match-card-{match.id}",
    )
    ds.sse.patch_elements(
        w,
        render_connected_modal(other),
        mode="outer",
        selector="#match-modal",
    )


# Intros land in the partner's real inbox, so they get a hard length cap and a
# per-(profile pair, sender) throttle on the shared Redis limiter. The key is
# the profile pair, never match.id — a deleted/re-created match must not reset it.
_INTRO_MAX_LEN = 2000
_INTRO_RL_MAX = 5
_INTRO_RL_WINDOW = 3600


def _intro_rl_key(match: Match, sender: Profile) -> str:
    """Rate-limit key: sorted profile pair + sender, stable across rematches."""
    a, b = sorted((str(match.profile_a_id), str(match.profile_b_id)))
    return f"rl:intro:{a}:{b}:{sender.id}"


async def intro(c: Context, w: Writer) -> None:
    """POST /intro — send a capped, throttled intro message on a match."""
    if reject_anonymous(c, w):
        return

    profile = await _require_profile(c, w)
    if profile is None:
        return

    form = await parse_form(c)
    body = form.get("body", "")
    if not body.strip():
        if _is_datastar(c):
            ds.sse.patch_elements(
                w,
                render_intro_status("Write a short intro first — don't send it empty."),
                mode="outer",
                selector="#intro-sent",
            )
            return
        responses.text(w, "Intro body is required.", status=400)
        return
    if len(body) > _INTRO_MAX_LEN:
        if _is_datastar(c):
            ds.sse.patch_elements(
                w,
                render_intro_status(
                    f"Too long — keep your intro under {_INTRO_MAX_LEN} characters."
                ),
                mode="outer",
                selector="#intro-sent",
            )
            return
        responses.text(w, "Intro is too long.", status=400)
        return

    match_id = await _match_id_from_request(c)
    if match_id is None:
        responses.text(w, "Invalid match.", status=400)
        return

    async with async_session() as db:
        # Pin the sender's profile before the match row — the same order an
        # account deletion locks them — so a delete in flight either finishes
        # first (the row comes back gone) or waits for this write to commit,
        # never a deadlock on opposite lock orders.
        if await lock_profile(db, profile.id) is None:
            responses.text(w, "Unauthorized", status=401)
            return
        match = await get_match_for_profile(db, match_id, profile)
        if match is None:
            responses.text(w, "Match not found.", status=404)
            return
        if await rate_limited(
            _intro_rl_key(match, profile), _INTRO_RL_MAX, _INTRO_RL_WINDOW
        ):
            if _is_datastar(c):
                ds.sse.patch_elements(
                    w,
                    render_intro_status(
                        "Slow down — give them a moment to reply first."
                    ),
                    mode="outer",
                    selector="#intro-sent",
                )
                return
            responses.text(w, "Too many intros. Try again later.", status=429)
            return
        other = await send_intro(db, match, profile, body.strip())
        if other is None:
            responses.text(w, "Match not found.", status=404)
            return

    if not _is_datastar(c):
        responses.text(w, "Intro sent")
        return

    ds.sse.patch_elements(
        w,
        render_intro_status(f"Intro sent to {other.name} — they're notified by email."),
        mode="outer",
        selector="#intro-sent",
    )
    ds.sse.patch_signals(w, {"introBody": ""})