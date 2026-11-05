# shipswipe-server

Stario 3.4 backend (Python 3.14, own asyncio server — not ASGI), Postgres via
SQLAlchemy async + asyncpg, Redis for sessions/rate limits.

## Setup

```bash
uv sync
```

Config comes from env (`config.py`): `DATABASE_URL` (default
`postgresql+asyncpg://localhost:5433/shipswipe`), `REDIS_URL`,
`MAGIC_LINK_SECRET`, `BASE_URL`, `APP_ENV`, `SMTP_*`.

## Run

```bash
uv run stario watch main:bootstrap    # dev, reloads on file change
uv run stario serve main:bootstrap    # production-style
```

## Test

```bash
uv run pytest -q
```

Tests run against `shipswipe_test` on Postgres `localhost:5433` (schema via
`Base.metadata.create_all`, see `tests/conftest.py`) and Redis db 15.
CI (`.github/workflows/test.yml`) runs the same suite on push/PR to `main`
against Postgres 16 + Redis 7 service containers.

## Migrations (Alembic)

Migrations live in `server/alembic/` (Alembic's conventional location; the plan
doc's `server/alembic/` entry refers to this directory). `alembic.ini` sits in
`server/`; `alembic/env.py` reads `DATABASE_URL` from the environment with the
same fallback as `config.py`, and imports `models.py` for autogenerate.

```bash
uv run alembic upgrade head                 # migrate DATABASE_URL to latest
uv run alembic history                      # list revisions
uv run alembic revision --autogenerate -m "…"  # new revision from models.py diff
uv run alembic upgrade head --sql           # offline SQL (no DB connection needed)
```

Run all of these from `server/`. In prod, `deploy_backend.sh` runs
`alembic upgrade head` on the box after `uv sync` and before the restart; the
prod `DATABASE_URL` comes from `/etc/shipswipe.env`.
