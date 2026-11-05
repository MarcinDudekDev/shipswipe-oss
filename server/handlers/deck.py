"""Deck, swipe, and undo handlers."""

from __future__ import annotations

import uuid

from stario import datastar as ds
from stario import responses
from stario.http.context import Context
from stario.http.writer import Writer

from auth.gate import current_user, reject_anonymous
from db import async_session
from models import Profile
from services.deck import deck_candidates
from services.forms import clean_field, parse_form, safe_signals, str_field
from services.matching import get_match_between, record_swipe, undo_last_swipe
from services.profile import get_profile_for_user
from views.deck import render_deck, render_match_modal, render_toast


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


async def _parse_swipe_payload(c: Context) -> tuple[str, str]:
    """Read target_id and direction from form fields or Datastar signals."""
    form = await parse_form(c)
    raw_target = str_field(form, "target_id", "targetId")
    direction = str_field(form, "direction")

    if not raw_target or not direction:
        signals = await safe_signals(c)
        if not raw_target:
            raw_target = str_field(signals, "target_id", "targetId")
        if not direction:
            direction = str_field(signals, "direction")

    return raw_target, direction


def _is_datastar(c: Context) -> bool:
    """True when the request came from a Datastar fetch action (@post & co.)."""
    return c.req.headers.get("datastar-request") is not None


async def deck(c: Context, w: Writer) -> None:
    """GET /deck — render the swipe deck partial."""
    if reject_anonymous(c, w):
        return

    profile = await _require_profile(c, w)
    if profile is None:
        return

    filter_param = clean_field(c.req.query.get("filter")) or "all"
    async with async_session() as db:
        candidates = await deck_candidates(db, profile, filter_param=filter_param)
    responses.html(w, render_deck(candidates, show_actions=True))


async def swipe(c: Context, w: Writer) -> None:
    """POST /swipe — record the swipe and patch deck, modal, or toast."""
    if reject_anonymous(c, w):
        return

    profile = await _require_profile(c, w)
    if profile is None:
        return

    raw_target, direction = await _parse_swipe_payload(c)
    try:
        target_id = uuid.UUID(raw_target)
    except ValueError:
        responses.text(w, "Invalid target.", status=400)
        return

    filter_param = clean_field(c.req.query.get("filter")) or "all"
    matched_profile: Profile | None = None
    matched_match_id = None
    target_profile: Profile | None = None

    async with async_session() as db:
        outcome = await record_swipe(db, profile, target_id, direction)
        if outcome == "gone":
            # A referenced profile was deleted mid-swipe. If ours is gone
            # the account is being deleted — treat as signed out; otherwise
            # the target vanished — it is simply no longer available.
            if await db.get(Profile, profile.id) is None:
                responses.text(w, "Unauthorized", status=401)
            elif _is_datastar(c):
                # A bare 404 leaves the card looking stuck — say why in the
                # toast the page already renders.
                ds.sse.patch_elements(
                    w,
                    render_toast("That profile is no longer available."),
                    mode="outer",
                    selector="#toast",
                )
            else:
                responses.text(w, "That profile is no longer available.", status=404)
            return
        if outcome == "match":
            target_profile = await db.get(Profile, target_id)
            matched_profile = target_profile
            match = await get_match_between(db, profile.id, target_id)
            matched_match_id = match.id if match is not None else None
        elif outcome == "recorded" and direction == "like":
            target_profile = await db.get(Profile, target_id)
        candidates = await deck_candidates(db, profile, filter_param=filter_param)

    ds.sse.patch_elements(
        w,
        render_deck(candidates, show_actions=True),
        mode="outer",
        selector="#deck",
    )
    if matched_profile is not None:
        ds.sse.patch_elements(
            w,
            render_match_modal(matched_profile, matched_match_id),
            mode="outer",
            selector="#match-modal",
        )
    elif direction == "like":
        if outcome == "matched":
            # Already a match (e.g. an undo that kept the conversation):
            # "interest sent" would promise a state they already have.
            message = "You're already matched — find them under Matches."
        elif target_profile is not None:
            # Interest recorded but no mutual match yet — confirm it landed so
            # the profile doesn't feel like it vanished. It lives under
            # /interested now.
            message = (
                f"Interest sent — you'll connect if {target_profile.name} is "
                "interested back. Find them under Interested."
            )
        else:
            # Rejected swipes must not echo the target's name — the toast can't
            # be a "does this profile exist" oracle.
            message = "Couldn't send interest on that profile."
        ds.sse.patch_elements(
            w,
            render_toast(message),
            mode="outer",
            selector="#toast",
        )


async def undo(c: Context, w: Writer) -> None:
    """POST /undo — remove the last swipe and re-render the deck."""
    if reject_anonymous(c, w):
        return

    profile = await _require_profile(c, w)
    if profile is None:
        return

    async with async_session() as db:
        await undo_last_swipe(db, profile)

    responses.empty(w, status=204)