"""Profile persistence helpers."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db import is_fk_violation
from models import Profile, ProfileTag, User


class ProfileGone(Exception):
    """The profile (or its user) was deleted while a write was in flight."""


async def get_profile_for_user(db: AsyncSession, user_id: uuid.UUID) -> Profile | None:
    """Return the profile owned by a user, or None."""
    result = await db.execute(sa.select(Profile).where(Profile.user_id == user_id))
    return result.scalar_one_or_none()


async def lock_profile(db: AsyncSession, profile_id: uuid.UUID) -> Profile | None:
    """SELECT ... FOR UPDATE on a profile row; None when the row is gone.

    Writers that touch a profile's child rows lock it first, in the same
    order account deletion does, so the two serialise instead of the
    insert tripping the row's foreign keys mid-delete.
    """
    result = await db.execute(
        sa.select(Profile).where(Profile.id == profile_id).with_for_update()
    )
    return result.scalar_one_or_none()


async def get_tags_csv(db: AsyncSession, profile_id: uuid.UUID) -> str:
    """Return a profile's tags as a comma-separated string."""
    rows = await db.execute(
        sa.select(ProfileTag.tag).where(ProfileTag.profile_id == profile_id)
    )
    return ", ".join(sorted(rows.scalars().all()))


def profile_is_complete(profile: Profile | None) -> bool:
    """A profile is deck-ready once it carries what to build and who it wants."""
    return bool(
        profile
        and (profile.building or "").strip()
        and (profile.looking_for or "").strip()
    )


async def upsert_profile(
    db: AsyncSession,
    user: User,
    *,
    role: str,
    name: str,
    bio: str,
    building: str,
    looking_for: str,
    terms: str,
    tags: str,
) -> Profile:
    """Create or update a profile, preserving moderation state.

    Parallel saves of the same profile can't crash on uniqueness: the row
    itself is a single INSERT ... ON CONFLICT (user_id) DO UPDATE — a
    concurrent first save waits and then takes the update path instead of
    hitting the unique index. visibility is deliberately not in the SET
    clause, so a member save never un-hides a profile that ops hid; only a
    brand-new row starts out live.

    Raises ProfileGone when the account was deleted underneath the save —
    the upsert then fails the user/profile foreign key, or the row it
    locked comes back deleted.
    """
    stmt = (
        pg_insert(Profile)
        .values(
            user_id=user.id,
            role=role,
            name=name,
            bio=bio,
            building=building,
            looking_for=looking_for,
            terms=terms,
            visibility="live",
        )
        .on_conflict_do_update(
            index_elements=["user_id"],
            set_={
                "role": role,
                "name": name,
                "bio": bio,
                "building": building,
                "looking_for": looking_for,
                "terms": terms,
            },
        )
        .returning(Profile.id)
    )
    try:
        profile_id = (await db.execute(stmt)).scalar_one()
    except IntegrityError as exc:
        if is_fk_violation(exc):
            raise ProfileGone from exc
        raise
    # Serialize the tag swap on the profile row: a parallel save blocks here
    # until the winner commits, then sees its committed tags — delete-then-
    # insert can no longer collide on profile_tags_profile_id_tag_key. The
    # same wait happens when account deletion holds the row — but its commit
    # removes the row entirely, so the lock coming back empty is a signal,
    # not something to write under.
    profile = (
        await db.execute(
            sa.select(Profile).where(Profile.id == profile_id).with_for_update()
        )
    ).scalar_one_or_none()
    if profile is None:
        raise ProfileGone
    await _replace_tags(db, profile.id, tags)
    await db.commit()
    # Refresh by re-selecting, not db.refresh: the row may have been deleted
    # between our commit and this read, and refresh raises instead of
    # returning None.
    profile = (
        await db.execute(sa.select(Profile).where(Profile.id == profile_id))
    ).scalar_one_or_none()
    if profile is None:
        raise ProfileGone
    return profile


async def _replace_tags(db: AsyncSession, profile_id: uuid.UUID, tags_csv: str) -> None:
    """Swap a profile's tag rows for a parsed comma-separated list.

    (profile_id, tag) is unique, so normalise first: strip, then keep the
    first spelling of each tag case-insensitively — "growth, growth, Growth"
    is one tag, and a plain typo can't trip the constraint with a 500.
    """
    await db.execute(sa.delete(ProfileTag).where(ProfileTag.profile_id == profile_id))
    seen: set[str] = set()
    for raw in tags_csv.split(","):
        tag = raw.strip()
        if tag and tag.casefold() not in seen:
            seen.add(tag.casefold())
            db.add(ProfileTag(profile_id=profile_id, tag=tag))


def profile_text(profile: Profile) -> str:
    """Return the profile's display fields joined as searchable text."""
    parts = [
        profile.name,
        profile.bio or "",
        profile.building or "",
        profile.looking_for or "",
        profile.role,
        profile.terms,
    ]
    return "\n".join(parts)