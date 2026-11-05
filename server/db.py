"""Async SQLAlchemy engine and session factory."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    poolclass=NullPool,
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def is_fk_violation(exc: IntegrityError) -> bool:
    """True for a foreign-key violation — a row the write referenced is gone.

    Postgres reports it as sqlstate 23503; on this codebase that means an
    account deletion committed underneath the in-flight write.
    """
    orig = getattr(exc, "orig", None)
    return (
        getattr(orig, "sqlstate", None) == "23503"
        or type(orig).__name__ == "ForeignKeyViolationError"
    )