"""Postgres ORM models for ShipSwipe."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base shared by all ORM models."""
    pass


class User(Base):
    """An account: sign-in identity, lifecycle and access state."""
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(sa.String(320), unique=True, nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    status: Mapped[str] = mapped_column(sa.String(32), default="active")
    is_admin: Mapped[bool] = mapped_column(sa.Boolean, default=False)


class Profile(Base):
    """A member's public matching profile and moderation state."""
    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), unique=True, nullable=False
    )
    role: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(255), default="")
    label: Mapped[str | None] = mapped_column(sa.String(255))
    bio: Mapped[str | None] = mapped_column(sa.Text)
    building: Mapped[str | None] = mapped_column(sa.Text)
    looking_for: Mapped[str | None] = mapped_column(sa.Text)
    terms: Mapped[str] = mapped_column(sa.String(32), default="flexible")
    visibility: Mapped[str] = mapped_column(sa.String(32), default="live")
    trust_level: Mapped[int] = mapped_column(sa.Integer, default=0)


class ProfileTag(Base):
    """A single interest/industry tag on a profile."""
    __tablename__ = "profile_tags"
    __table_args__ = (sa.UniqueConstraint("profile_id", "tag"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("profiles.id"), nullable=False
    )
    tag: Mapped[str] = mapped_column(sa.String(64), nullable=False)


class Swipe(Base):
    """A recorded like or pass from one profile toward another."""
    __tablename__ = "swipes"
    __table_args__ = (
        sa.UniqueConstraint("swiper_profile_id", "target_profile_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    swiper_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("profiles.id"), nullable=False
    )
    target_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("profiles.id"), nullable=False
    )
    direction: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


class Match(Base):
    """A mutual like between two profiles, plus its connect state."""
    __tablename__ = "matches"
    __table_args__ = (sa.UniqueConstraint("profile_a_id", "profile_b_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    profile_a_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("profiles.id"), nullable=False
    )
    profile_b_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("profiles.id"), nullable=False
    )
    connected_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


class Message(Base):
    """An intro message exchanged on a match."""
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    match_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("matches.id"), nullable=False
    )
    sender_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("profiles.id"), nullable=False
    )
    body: Mapped[str] = mapped_column(sa.Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    read_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))