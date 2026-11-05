"""Discover page handler — login required."""

from __future__ import annotations

from stario import responses
from stario.http.context import Context
from stario.http.writer import Writer

from auth.gate import current_user, require_user_page
from db import async_session
from models import Profile
from services.deck import deck_candidates
from services.forms import clean_field
from services.profile import get_profile_for_user
from views.discover import render_discover_page


async def discover(c: Context, w: Writer) -> None:
    """GET /discover — render the members' swipe deck page."""
    if require_user_page(c, w):
        return

    filter_param = clean_field(c.req.query.get("filter")) or "all"
    user = current_user(c)

    async with async_session() as db:
        profile = await get_profile_for_user(db, user.id)
        if profile is None:
            candidates: list[Profile] = []
        else:
            candidates = await deck_candidates(db, profile, filter_param=filter_param)

    responses.html(w, render_discover_page(candidates))
