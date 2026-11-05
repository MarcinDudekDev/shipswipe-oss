"""Shared test fixtures.

App modules (config, db, models, services, main) are imported inside fixtures and
test bodies, not at module top level, so a broken import fails the affected tests
instead of aborting collection of the whole suite.
"""

import asyncio
import os

import pytest

TEST_DB = "shipswipe_test"
# Local Homebrew postgresql@16 listens on 5433 here (not the default 5432).
PG_HOST = os.environ.get("PGHOST", "localhost")
PG_PORT = os.environ.get("PGPORT", "5433")
DEFAULT_DB_URL = f"postgresql+asyncpg://{PG_HOST}:{PG_PORT}/{TEST_DB}"
DEFAULT_REDIS_URL = "redis://localhost:6379/15"


def _ensure_test_database() -> None:
    """Create the throwaway test database if it doesn't exist (idempotent)."""
    import asyncpg

    async def _go():
        try:
            conn = await asyncpg.connect(host=PG_HOST, port=int(PG_PORT), database="postgres")
        except Exception:
            conn = await asyncpg.connect(
                host=PG_HOST, port=int(PG_PORT), database=os.environ.get("USER", "postgres")
            )
        try:
            exists = await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1", TEST_DB
            )
            if not exists:
                await conn.execute(f'CREATE DATABASE "{TEST_DB}"')
        finally:
            await conn.close()

    asyncio.run(_go())


@pytest.fixture(scope="session", autouse=True)
def _test_env():
    os.environ["APP_ENV"] = "test"
    os.environ.setdefault("PGHOST", PG_HOST)
    os.environ.setdefault("PGPORT", PG_PORT)
    os.environ.setdefault("DATABASE_URL", DEFAULT_DB_URL)
    # The schema fixture runs drop_all. Refuse to touch any database that is not
    # clearly a throwaway test database, whatever DATABASE_URL the shell exported.
    db_name = os.environ["DATABASE_URL"].rsplit("/", 1)[-1].split("?", 1)[0]
    if not db_name.endswith("_test"):
        pytest.exit(
            f"refusing to run tests against database {db_name!r}: "
            "DATABASE_URL must point at a database whose name ends in _test",
            returncode=2,
        )
    os.environ.setdefault("REDIS_URL", DEFAULT_REDIS_URL)
    os.environ.setdefault("MAGIC_LINK_SECRET", "test-secret-do-not-use-in-prod")
    os.environ.setdefault("BASE_URL", "http://testserver")
    _ensure_test_database()
    yield


@pytest.fixture
async def schema():
    """Drop + recreate all tables for isolation. Depended on by db/client only,
    so DB-free tests (e.g. the cp0 smoke suite) stay decoupled from the data layer."""
    from db import engine  # impl-provided
    from models import Base  # impl-provided

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest.fixture(autouse=True)
def _clear_outbox():
    """Email outbox is captured (not sent) in test mode; reset between tests."""
    try:
        from services.email import OUTBOX

        OUTBOX.clear()
    except Exception:
        pass
    yield


@pytest.fixture
async def db(schema):
    """An async SQLAlchemy session bound to the test database (fresh schema)."""
    from db import async_session  # impl-provided

    async with async_session() as session:
        yield session


@pytest.fixture
async def client(schema):
    """A Stario TestClient driving the real app against the test database/redis."""
    import main  # impl-provided (bootstrap)
    from stario.testing import TestClient

    async with TestClient(main.bootstrap) as c:
        yield c


# ---- helpers usable by tests -------------------------------------------------

def last_magic_link() -> str:
    """Return the verify URL from the most recent captured email, or '' if none."""
    from services.email import OUTBOX

    if not OUTBOX:
        return ""
    msg = OUTBOX[-1]
    # accept either an explicit 'link' field or a URL embedded in the body
    if isinstance(msg, dict):
        if msg.get("link"):
            return msg["link"]
        body = msg.get("body", "") or ""
    else:
        body = str(msg)
    for token in body.replace("\n", " ").split():
        if "/auth/verify" in token:
            return token.strip("<>\"')")
    return ""


async def login(client, email: str):
    """Full magic-link login: request a link, then follow it. Returns the response."""
    await client.post("/auth/request-link", data={"email": email})
    link = last_magic_link()
    assert link, "no magic link was captured in the outbox"
    # normalise absolute -> path for the test client
    path = link.split("testserver", 1)[-1] if "testserver" in link else link
    # GET renders the confirm page (mail scanners prefetch links); POST signs in.
    page = await client.get(path)
    if page.status_code != 200 or "token=" not in path:
        return page
    return await client.post("/auth/verify", data={"token": path.split("token=", 1)[1]})


async def make_profile(client, role="builder", name="Me", bio="hi there",
                       building="a thing", looking_for="a growth partner",
                       terms="rev-share", tags="React,SEO"):
    """Create/update the logged-in user's profile via the API."""
    return await client.post("/profile", data={
        "role": role, "name": name, "bio": bio, "building": building,
        "looking_for": looking_for, "terms": terms, "tags": tags,
    })


async def profile_for_email(db, email: str):
    """Return the Profile row owned by the user with this email (or None)."""
    import sqlalchemy as sa
    from models import Profile, User

    res = await db.execute(
        sa.select(Profile).join(User, Profile.user_id == User.id).where(User.email == email)
    )
    return res.scalar_one_or_none()


async def seed_user_profile(db, role, name, terms="flexible",
                            building="seed thing", looking_for="seed partner"):
    """Insert a verified user + profile directly (a counterpart to swipe on). Returns Profile."""
    import uuid
    from datetime import datetime, timezone
    from models import Profile, User

    user = User(email=f"{uuid.uuid4().hex}@example.com",
                email_verified_at=datetime.now(timezone.utc))
    db.add(user)
    await db.flush()
    p = Profile(user_id=user.id, role=role, name=name, terms=terms,
                building=building, looking_for=looking_for, bio="seed bio")
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


async def seed_like(db, swiper_profile_id, target_profile_id):
    """Record an existing 'like' from one profile toward another."""
    from models import Swipe

    db.add(Swipe(swiper_profile_id=swiper_profile_id,
                 target_profile_id=target_profile_id, direction="like"))
    await db.commit()


async def seed_match(db, profile_a_id, profile_b_id):
    """Insert a Match row directly (ids stored sorted, mirroring the impl). Returns Match."""
    from models import Match

    a, b = sorted([profile_a_id, profile_b_id], key=str)
    m = Match(profile_a_id=a, profile_b_id=b)
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return m


async def latest_match_id(db):
    """Return the id of the most recently created match, or None."""
    import sqlalchemy as sa
    from models import Match

    return (await db.execute(
        sa.select(Match.id).order_by(Match.created_at.desc()).limit(1)
    )).scalar_one_or_none()
