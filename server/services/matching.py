"""Swipe, match, undo, connect, and intro logic."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth.redis_client import get_redis
from db import is_fk_violation
from models import Match, Message, Profile, Swipe, User
from services import email as email_service
from services.deck import matched_partner_ids, valid_swipe_target

# A pair is told "you matched" at most once, ever — re-created matches (undo,
# pass/like cycling) must never re-email or the notification becomes a bomb.
_MATCH_NOTIFY_TTL = 365 * 24 * 3600


async def record_swipe(
    db: AsyncSession,
    swiper: Profile,
    target_id: uuid.UUID,
    direction: str,
) -> str:
    """Record a swipe and check for a mutual match.

    Returns "match" (a new mutual match was created), "matched" (the like
    landed on a pair that is already matched), "recorded" (the swipe was
    stored on a valid target), "ignored" (bad direction or a target
    that isn't a valid deck candidate), or "gone" (a referenced profile
    was deleted mid-write) so callers can tell a real like from
    a rejected swipe — and not leak the target's name either way.
    """
    # Serialise the pair for the whole transaction: without it, two
    # simultaneous mutual likes write-skew — each commits a like neither saw
    # the other's, so no match is ever created. The lock key is the sorted
    # pair, so both directions queue on the same lock and the second like's
    # reciprocal check sees the first's committed swipe.
    a_id, b_id = sorted((str(swiper.id), str(target_id)))
    await db.execute(
        sa.select(
            sa.func.pg_advisory_xact_lock(sa.func.hashtext(f"{a_id}:{b_id}"))
        )
    )

    if direction not in ("like", "pass"):
        return "ignored"

    if await valid_swipe_target(db, swiper, target_id) is None:
        return "ignored"

    # Pin both profile rows FOR KEY SHARE, in id order, before any child row
    # is written. The swipe insert's foreign-key checks would take this same
    # lock anyway — but only after the upsert already holds a lock on the
    # swipe row, which is exactly the ordering account deletion inverts (it
    # holds its profile FOR UPDATE, then reaps the swipe/match rows beneath
    # it). Locking the pair up front turns that deadlock into a wait: the
    # delete blocks on our key share, or we block on its update lock and find
    # the row gone afterwards.
    pair = (
        (
            await db.execute(
                sa.select(Profile)
                .where(Profile.id.in_([swiper.id, target_id]))
                .order_by(Profile.id)
                .with_for_update(key_share=True)
            )
        )
        .scalars()
        .all()
    )
    if len(pair) < 2:
        await db.rollback()
        return "gone"

    # INSERT ... ON CONFLICT DO UPDATE: concurrent identical swipes (a double
    # tap, a retried request) hit the (swiper, target) unique index together —
    # the loser updates in place instead of crashing on a second INSERT.
    # Re-swiping also rewrites the direction before any match check, so a
    # like after a pass still counts.
    stmt = (
        pg_insert(Swipe)
        .values(
            swiper_profile_id=swiper.id,
            target_profile_id=target_id,
            direction=direction,
        )
        .on_conflict_do_update(
            index_elements=["swiper_profile_id", "target_profile_id"],
            set_={"direction": direction},
        )
    )
    try:
        await db.execute(stmt)
    except IntegrityError as exc:
        # Both profiles are already pinned FOR KEY SHARE above, so an FK
        # violation here should be unreachable — keep the mapping anyway as
        # the last line of defence against a profile vanishing mid-write.
        if is_fk_violation(exc):
            await db.rollback()
            return "gone"
        raise

    if direction != "like":
        # A pass only rewrites the swipe row: the match — and its messages —
        # belongs to both members and must outlive one side's swipe flip.
        await db.commit()
        return "recorded"

    await db.flush()

    reciprocal = await db.execute(
        sa.select(Swipe).where(
            Swipe.swiper_profile_id == target_id,
            Swipe.target_profile_id == swiper.id,
            Swipe.direction == "like",
        )
    )
    if reciprocal.scalar_one_or_none() is None:
        await db.commit()
        return "recorded"

    created = await _create_match(db, swiper.id, target_id)
    if created:
        return "match"
    # Mutual likes can land on a match that already exists (an undo kept the
    # conversation, or pass/like cycling): the swipe still records, but it is
    # not a fresh connection and "interest sent" would be a lie.
    return "matched" if await get_match_between(db, swiper.id, target_id) else "recorded"


async def _create_match(
    db: AsyncSession,
    profile_a: uuid.UUID,
    profile_b: uuid.UUID,
) -> bool:
    """Create the match row for a mutual like, once."""
    a_id, b_id = sorted([profile_a, profile_b], key=str)
    stmt = (
        pg_insert(Match)
        .values(profile_a_id=a_id, profile_b_id=b_id)
        .on_conflict_do_nothing()
        .returning(Match.id)
    )
    result = await db.execute(stmt)
    created = result.scalar_one_or_none() is not None
    await db.commit()

    if created:
        # The match row can be deleted and re-created (undo with no messages);
        # the notification can't — claim the pair's one-shot credit first.
        claimed = await get_redis().set(
            f"notified:match:{a_id}:{b_id}", "1", nx=True, ex=_MATCH_NOTIFY_TTL
        )
        if claimed:
            await _notify_match(db, a_id, b_id)
    return created


async def _notify_match(
    db: AsyncSession,
    profile_a_id: uuid.UUID,
    profile_b_id: uuid.UUID,
) -> None:
    """Email both members that they matched."""
    profiles = (
        await db.execute(
            sa.select(Profile, User.email)
            .join(User, User.id == Profile.user_id)
            .where(Profile.id.in_([profile_a_id, profile_b_id]))
        )
    ).all()
    for profile, email in profiles:
        other_name = next(
            (p.name for p, _ in profiles if p.id != profile.id),
            "someone",
        )
        await email_service.send_async(
            to=email,
            subject="You have a new match on ShipSwipe",
            body=f"You matched with {other_name}!",
            link="/matches",
        )


async def undo_last_swipe(db: AsyncSession, swiper: Profile) -> bool:
    """Remove the most recent swipe; a like takes its match only when the
    match is still silent — once messages exist, undo removes the swipe but
    the conversation (both members' data) stays."""
    result = await db.execute(
        sa.select(Swipe)
        .where(Swipe.swiper_profile_id == swiper.id)
        .order_by(Swipe.created_at.desc())
        .limit(1)
    )
    swipe = result.scalar_one_or_none()
    if swipe is None:
        return False
    # The same pair lock record_swipe holds while it checks the reciprocal
    # like. Without it, an undo racing the partner's like can commit its
    # delete after the partner's reciprocal check already saw the like —
    # leaving a match backed by only one side.
    a_id, b_id = sorted((str(swiper.id), str(swipe.target_profile_id)))
    await db.execute(
        sa.select(
            sa.func.pg_advisory_xact_lock(sa.func.hashtext(f"{a_id}:{b_id}"))
        )
    )
    # The swipe may have vanished while the lock was waited on (another
    # undo, an account deletion) — re-read inside the lock. populate_existing
    # reloads the identity-mapped row instead of returning it stale: a
    # direction flipped like->pass by a re-swipe while we waited must be
    # seen, or undo deletes a match a "pass" is meant to keep.
    swipe = (
        await db.execute(
            sa.select(Swipe)
            .where(Swipe.id == swipe.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if swipe is None:
        await db.rollback()
        return False
    if swipe.direction == "like":
        match = await get_match_between(db, swiper.id, swipe.target_profile_id)
        if match is not None:
            messages = await db.scalar(
                sa.select(sa.func.count())
                .select_from(Message)
                .where(Message.match_id == match.id)
            )
            if not messages:
                # A quiet match is a phantom once the like is gone — drop it.
                # Messages are never deleted on undo.
                await db.delete(match)
    await db.delete(swipe)
    await db.commit()
    return True


async def list_rejected(db: AsyncSession, my_profile: Profile) -> list[Profile]:
    """Profiles this user rejected that are still live — candidates to reconsider.

    A matched partner stays off this page even when they hold a pass swipe:
    a pass/like cycle can record one while the match outlives it.
    """
    result = await db.execute(
        sa.select(Profile)
        .join(Swipe, Swipe.target_profile_id == Profile.id)
        .where(
            Swipe.swiper_profile_id == my_profile.id,
            Swipe.direction == "pass",
            Profile.visibility == "live",
            Profile.id.not_in(matched_partner_ids(my_profile)),
        )
        .order_by(Swipe.created_at.desc())
    )
    return list(result.scalars().unique().all())


async def reconsider_swipe(
    db: AsyncSession,
    my_profile: Profile,
    target_id: uuid.UUID,
) -> bool:
    """Undo a single rejection so the target returns to the deck. Returns True if removed."""
    result = await db.execute(
        sa.select(Swipe).where(
            Swipe.swiper_profile_id == my_profile.id,
            Swipe.target_profile_id == target_id,
            Swipe.direction == "pass",
        )
    )
    swipe = result.scalar_one_or_none()
    if swipe is None:
        return False
    await db.delete(swipe)
    await db.commit()
    return True


async def list_interested(db: AsyncSession, my_profile: Profile) -> list[Profile]:
    """Profiles I expressed interest in (like) that haven't become a match yet.

    These sit in limbo otherwise: gone from the deck, not rejected, not yet a
    match — awaiting the other side to be interested back.
    """
    result = await db.execute(
        sa.select(Profile)
        .join(Swipe, Swipe.target_profile_id == Profile.id)
        .where(
            Swipe.swiper_profile_id == my_profile.id,
            Swipe.direction == "like",
            Profile.visibility == "live",
            Profile.id.not_in(matched_partner_ids(my_profile)),
        )
        .order_by(Swipe.created_at.desc())
    )
    return list(result.scalars().unique().all())


async def list_matches(db: AsyncSession, my_profile: Profile) -> list[tuple[Match, Profile]]:
    """Return (match, counterpart profile) rows for a profile, newest first."""
    other_id = sa.case(
        (Match.profile_a_id == my_profile.id, Match.profile_b_id),
        else_=Match.profile_a_id,
    )
    result = await db.execute(
        sa.select(Match, Profile)
        .join(Profile, Profile.id == other_id)
        .where(
            sa.or_(
                Match.profile_a_id == my_profile.id,
                Match.profile_b_id == my_profile.id,
            )
        )
        .order_by(Match.created_at.desc())
    )
    return list(result.all())


async def get_match_between(
    db: AsyncSession,
    profile_a: uuid.UUID,
    profile_b: uuid.UUID,
) -> Match | None:
    """Fetch the Match row for a pair of profiles (ids stored str-sorted).

    Takes the row FOR UPDATE: a match that is about to be deleted (an undo,
    an account deletion) either finishes before the lock is granted —
    the lookup then finds nothing — or waits for this transaction, so a
    concurrent intro never inserts a message into a half-deleted match.
    """
    a_id, b_id = sorted([profile_a, profile_b], key=str)
    result = await db.execute(
        sa.select(Match)
        .where(
            Match.profile_a_id == a_id,
            Match.profile_b_id == b_id,
        )
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def get_other_profile(
    db: AsyncSession,
    match: Match,
    my_profile: Profile,
) -> Profile | None:
    """The profile on the other side of a match."""
    other_id = (
        match.profile_b_id
        if match.profile_a_id == my_profile.id
        else match.profile_a_id
    )
    return await db.get(Profile, other_id)


async def get_match_for_profile(
    db: AsyncSession,
    match_id: uuid.UUID,
    my_profile: Profile,
) -> Match | None:
    """Return the match between a profile and a counterpart, or None.

    Takes the row FOR UPDATE so an intro (or connect) on it serialises
    against a concurrent deletion: the deleter waits for this transaction
    instead of pulling the row out from under the message insert.
    """
    result = await db.execute(
        sa.select(Match)
        .where(
            Match.id == match_id,
            sa.or_(
                Match.profile_a_id == my_profile.id,
                Match.profile_b_id == my_profile.id,
            ),
        )
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def connect_match(db: AsyncSession, match: Match) -> None:
    """Mark a match as connected."""
    match.connected_at = datetime.now(timezone.utc)
    await db.commit()


async def send_intro(
    db: AsyncSession,
    match: Match,
    sender: Profile,
    body: str,
) -> Profile | None:
    """Persist an intro message on a match and notify the recipient.

    Returns the recipient profile, or None when the partner's profile is
    gone — the caller then answers 404 instead of writing into a match
    whose other member was just deleted.
    """
    other = await get_other_profile(db, match, sender)
    if other is None:
        return None

    db.add(
        Message(
            match_id=match.id,
            sender_profile_id=sender.id,
            body=body,
        )
    )
    await db.commit()

    other_user = await db.get(User, other.user_id)
    if other_user is not None:
        await email_service.send_async(
            to=other_user.email,
            subject="New intro on ShipSwipe",
            body=f"{sender.name} sent you an intro: {body}",
            link="/matches",
        )
    return other