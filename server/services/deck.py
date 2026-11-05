"""Discover deck query logic."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from models import Match, Profile, ProfileTag, Swipe

_OPPOSITE_ROLE = {"builder": "marketer", "marketer": "builder"}


def opposite_role(role: str) -> str:
    """Return the counterpart deck role for a member's role."""
    return _OPPOSITE_ROLE.get(role, role)


async def valid_swipe_target(
    db: AsyncSession,
    swiper: Profile,
    target_id: uuid.UUID,
) -> Profile | None:
    """Return the target profile only if it is a valid deck candidate."""
    if target_id == swiper.id:
        return None

    target = await db.get(Profile, target_id)
    if target is None:
        return None
    if target.role != opposite_role(swiper.role):
        return None
    if target.visibility != "live":
        return None
    return target


def matched_partner_ids(my_profile: Profile) -> sa.Select:
    """Subquery: profile ids currently matched with this member."""
    other = sa.case(
        (Match.profile_a_id == my_profile.id, Match.profile_b_id),
        else_=Match.profile_a_id,
    )
    return sa.select(other).where(
        sa.or_(
            Match.profile_a_id == my_profile.id,
            Match.profile_b_id == my_profile.id,
        )
    )


def _apply_deck_filter(stmt: sa.Select, filter_param: str) -> sa.Select:
    """Narrow the deck query by industry, tags, or name search."""
    if filter_param.startswith("terms:"):
        terms_value = filter_param.split(":", 1)[1]
        return stmt.where(Profile.terms == terms_value)
    if filter_param.startswith("tag:"):
        tag_value = filter_param.split(":", 1)[1]
        return stmt.join(ProfileTag, ProfileTag.profile_id == Profile.id).where(
            ProfileTag.tag == tag_value
        )
    return stmt


async def deck_candidates(
    db: AsyncSession,
    my_profile: Profile,
    *,
    filter_param: str = "all",
) -> list[Profile]:
    """Return unswiped live profiles on the opposite side, trust-first, capped."""
    swiped_ids = sa.select(Swipe.target_profile_id).where(
        Swipe.swiper_profile_id == my_profile.id
    )

    stmt = (
        sa.select(Profile)
        .where(
            Profile.id != my_profile.id,
            Profile.role == opposite_role(my_profile.role),
            Profile.visibility == "live",
            Profile.id.not_in(swiped_ids),
            # An undo can delete the swipe while a match with messages lives
            # on — a matched partner must never resurface in the deck.
            Profile.id.not_in(matched_partner_ids(my_profile)),
        )
        .order_by(Profile.trust_level.desc(), Profile.id)
        # Cap the deck: the full opposite side can't be loaded into ORM objects
        # on every /deck, /discover and /swipe as the table grows.
        .limit(200)
    )

    stmt = _apply_deck_filter(stmt, filter_param)

    result = await db.execute(stmt)
    return list(result.scalars().unique().all())