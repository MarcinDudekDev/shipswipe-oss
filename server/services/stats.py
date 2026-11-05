"""Homepage community stats."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from models import Match, Profile


async def homepage_stats(db: AsyncSession) -> dict[str, int]:
    """Live counts for the landing: registered builders, marketers, and matches."""

    async def _count(stmt: sa.Select) -> int:
        """Run a COUNT select and return it as an int."""
        return int((await db.execute(stmt)).scalar() or 0)

    def _role(role: str) -> sa.Select:
        """Build a COUNT select of live profiles with a given role."""
        return sa.select(sa.func.count()).select_from(Profile).where(
            Profile.role == role, Profile.visibility == "live"
        )

    return {
        "builders": await _count(_role("builder")),
        "marketers": await _count(_role("marketer")),
        "matches": await _count(sa.select(sa.func.count()).select_from(Match)),
    }
