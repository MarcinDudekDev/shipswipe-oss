"""The Alembic chain must build the real schema on a throwaway DB.

Runs `alembic upgrade head` against `shipswipe_alembic_test` (created/dropped
fresh here — the suite's `shipswipe_test` is never touched). This is a
sync test on purpose: env.py drives the async engine via asyncio.run(), which
cannot run inside an already-running event loop.
"""

import asyncio
import os
from pathlib import Path

import asyncpg
from alembic import command
from alembic.config import Config

SERVER_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_TEST_DB = "shipswipe_alembic_test"

PG_HOST = os.environ.get("PGHOST", "localhost")
PG_PORT = os.environ.get("PGPORT", "5433")


async def _admin_connect() -> asyncpg.Connection:
    try:
        return await asyncpg.connect(
            host=PG_HOST, port=int(PG_PORT), database="postgres"
        )
    except Exception:
        return await asyncpg.connect(
            host=PG_HOST,
            port=int(PG_PORT),
            database=os.environ.get("USER", "postgres"),
        )


async def _recreate_db() -> None:
    conn = await _admin_connect()
    try:
        await conn.execute(
            f'DROP DATABASE IF EXISTS "{ALEMBIC_TEST_DB}" WITH (FORCE)'
        )
        await conn.execute(f'CREATE DATABASE "{ALEMBIC_TEST_DB}"')
    finally:
        await conn.close()


async def _inspect_schema():
    conn = await asyncpg.connect(
        host=PG_HOST, port=int(PG_PORT), database=ALEMBIC_TEST_DB
    )
    try:
        tables = {
            r["table_name"]
            for r in await conn.fetch(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            )
        }
        uniques = {
            (r["table_name"], tuple(sorted(r["cols"])))
            for r in await conn.fetch(
                """
                SELECT conrelid::regclass::text AS table_name,
                       array_agg(att.attname) AS cols
                FROM pg_constraint con
                JOIN unnest(con.conkey) AS ord(attnum) ON true
                JOIN pg_attribute att
                  ON att.attrelid = con.conrelid AND att.attnum = ord.attnum
                WHERE con.contype = 'u'
                  AND con.connamespace = 'public'::regnamespace
                GROUP BY conrelid::regclass::text, con.conname
                """
            )
        }
    finally:
        await conn.close()
    return tables, uniques


def test_alembic_upgrade_head_builds_schema(monkeypatch):
    asyncio.run(_recreate_db())
    monkeypatch.setenv(
        "DATABASE_URL",
        f"postgresql+asyncpg://{PG_HOST}:{PG_PORT}/{ALEMBIC_TEST_DB}",
    )

    cfg = Config(str(SERVER_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(SERVER_DIR / "alembic"))
    command.upgrade(cfg, "head")

    tables, uniques = asyncio.run(_inspect_schema())

    assert {
        "users",
        "profiles",
        "profile_tags",
        "swipes",
        "matches",
        "messages",
    } <= tables
    assert ("users", ("email",)) in uniques
    assert ("swipes", ("swiper_profile_id", "target_profile_id")) in uniques
