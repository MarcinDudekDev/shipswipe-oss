"""Profile view and create/update handlers."""

from __future__ import annotations

from stario import responses
from stario.http.context import Context
from stario.http.writer import Writer

from auth.gate import current_user, reject_anonymous, require_user_page
from db import async_session
from services.forms import parse_form
from services.profile import (
    ProfileGone,
    get_profile_for_user,
    get_tags_csv,
    profile_is_complete,
    upsert_profile,
)
from views.profile import _TERMS, render_profile_page

_VALID_ROLES = {"builder", "marketer"}
_VALID_TERMS = {value for value, _ in _TERMS}

# Free-text fields are capped before the DB: unbounded input is both a
# storage bomb and an event-loop stall (multi-megabyte strings per request).
_NAME_MAX = 120
_BIO_MAX = 2000
_TEXT_MAX = 500
_TAGS_RAW_MAX = 1000
_TAGS_MAX_COUNT = 20
_TAGS_MAX_LEN = 40


async def profile_get(c: Context, w: Writer) -> None:
    """GET /profile — render the member's profile editor."""
    if require_user_page(c, w):
        return

    user = current_user(c)
    if user is None:
        responses.text(w, "Unauthorized", status=401)
        return

    async with async_session() as db:
        profile = await get_profile_for_user(db, user.id)
        tags = await get_tags_csv(db, profile.id) if profile else ""

    responses.html(
        w,
        render_profile_page(profile, complete=profile_is_complete(profile), tags=tags),
    )


async def profile_post(c: Context, w: Writer) -> None:
    """POST /profile — validate and save profile edits."""
    if reject_anonymous(c, w):
        return

    user = current_user(c)
    if user is None:
        responses.text(w, "Unauthorized", status=401)
        return

    form = await parse_form(c)
    role = form.get("role", "builder")
    terms = form.get("terms", "flexible")
    name = form.get("name", "").strip()
    bio = form.get("bio", "")
    building = form.get("building", "")
    looking_for = form.get("looking_for", "")
    tags = form.get("tags", "")
    if role not in _VALID_ROLES or terms not in _VALID_TERMS:
        responses.text(w, "Invalid profile values.", status=400)
        return
    if not name:
        responses.text(w, "Name is required.", status=400)
        return
    if len(name) > _NAME_MAX:
        responses.text(w, "Name is too long.", status=400)
        return
    if (
        len(bio) > _BIO_MAX
        or len(building) > _TEXT_MAX
        or len(looking_for) > _TEXT_MAX
    ):
        responses.text(w, "Profile text is too long.", status=400)
        return
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    if (
        len(tags) > _TAGS_RAW_MAX
        or len(tag_list) > _TAGS_MAX_COUNT
        or any(len(t) > _TAGS_MAX_LEN for t in tag_list)
    ):
        responses.text(w, "Tags are too long.", status=400)
        return

    async with async_session() as db:
        try:
            await upsert_profile(
                db,
                user,
                role=role,
                name=name,
                bio=bio,
                building=building,
                looking_for=looking_for,
                terms=terms,
                tags=tags,
            )
        except ProfileGone:
            # The account was deleted while this save was in flight — there
            # is no profile left to write, and the session is going with it.
            responses.text(w, "Unauthorized", status=401)
            return

    responses.redirect(w, "/discover", status=303)