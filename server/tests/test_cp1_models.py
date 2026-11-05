"""Checkpoint 1 — data model & persistence (Postgres via SQLAlchemy async).

The implementation must provide:
  - models.py : DeclarativeBase `Base` + ORM models User, Profile, Swipe, Match, Message
  - db.py     : async `engine` and `async_session` (sessionmaker) bound to DATABASE_URL
"""

import uuid

import pytest
import sqlalchemy as sa


def test_base_and_models_importable():
    from models import Base, User, Profile, Swipe, Match, Message

    tables = set(Base.metadata.tables)
    assert {"users", "profiles", "swipes", "matches", "messages"} <= tables


def test_profile_has_core_columns():
    from models import Profile

    cols = {c.name for c in Profile.__table__.columns}
    # role-aware partnership fields the cards/detail panel surface
    assert {"role", "name", "bio", "building", "looking_for", "terms"} <= cols


def test_user_email_is_unique():
    from models import User

    email_col = User.__table__.columns["email"]
    assert email_col.unique or any(
        isinstance(c, sa.UniqueConstraint) and "email" in c.columns
        for c in User.__table__.constraints
    )


async def test_can_persist_user_and_profile(db):
    from models import User, Profile

    user = User(email=f"{uuid.uuid4().hex}@example.com")
    db.add(user)
    await db.flush()
    profile = Profile(
        user_id=user.id, role="builder", name="Test Builder",
        bio="b", building="thing", looking_for="growth", terms="rev-share",
    )
    db.add(profile)
    await db.commit()

    got = await db.get(Profile, profile.id)
    assert got is not None
    assert got.role == "builder"


async def test_swipe_pair_is_unique(db):
    """One decision per (swiper, target) pair — enforced by a unique constraint."""
    from models import User, Profile, Swipe

    async def mk(role):
        u = User(email=f"{uuid.uuid4().hex}@example.com")
        db.add(u)
        await db.flush()
        p = Profile(user_id=u.id, role=role, name=role, terms="flexible")
        db.add(p)
        await db.flush()
        return p

    a = await mk("builder")
    b = await mk("marketer")
    db.add(Swipe(swiper_profile_id=a.id, target_profile_id=b.id, direction="like"))
    await db.commit()
    db.add(Swipe(swiper_profile_id=a.id, target_profile_id=b.id, direction="pass"))
    with pytest.raises(Exception):
        await db.commit()
