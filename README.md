# ShipSwipe

Members-only matching for product builders and growth marketers. Members
create a profile, swipe on the opposite side, and connect when the interest
is mutual. Sign-in is passwordless over emailed magic links.

The repo has two parts: a static marketing site at the root, and the app
backend in `server/`.

## Stack

- Python 3.14, managed with `uv`
- Stario 3.4 (server-rendered, no ASGI)
- Datastar v1.0.1 (vendored in `server/static/js/`) for reactive requests
  and SSE element patches
- SQLAlchemy async + asyncpg on PostgreSQL, Alembic for migrations
- Redis (>= 6.2 — the auth flow uses GETDEL) for sessions, magic-link
  tokens, and rate limits

## Local development

You need PostgreSQL and Redis running locally (the default config expects
Postgres on port 5433 and Redis on port 6379; override via env).

```bash
cd server
uv sync
uv run alembic upgrade head
uv run stario serve main:bootstrap --port 8787
```

Settings are read from the environment in `server/config.py`:

| Variable           | Default                                | Notes                          |
| ------------------ | -------------------------------------- | ------------------------------ |
| `APP_ENV`          | `development`                          | `development`, `test`, `production` |
| `DATABASE_URL`     | `postgresql+asyncpg://localhost:5433/shipswipe` |                       |
| `REDIS_URL`        | `redis://localhost:6379/0`             |                                |
| `MAGIC_LINK_SECRET`| `dev-secret-change-me`                 | see Security notes             |
| `BASE_URL`         | `http://localhost:8787`                | public origin of the app       |
| `CONTACT_EMAIL`    | `support@<BASE_URL host>`              | legal-pages data-subject contact |
| `SMTP_*`           | local capture                          | see below                      |

In development and test, outgoing email is captured in an in-memory OUTBOX
instead of hitting the network. In development the server also prints each
captured email's link to stdout, so the sign-in link is reachable without a
mailbox. In production, set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`,
`SMTP_PASSWORD`, and `SMTP_FROM` for real delivery.

## Tests

```bash
cd server
uv run pytest -q
```

The suite drops and recreates its tables, so `DATABASE_URL` must point at
a database whose name ends in `_test` — the fixtures refuse anything else
(and create `shipswipe_test` when it is unset). Tests use Redis database 15
and select `APP_ENV=test` automatically.

## Deployment

- `deploy.sh` builds the static marketing site into `dist/` and deploys it
  to Cloudflare Pages. It needs `CLOUDFLARE_API_KEY`, `CLOUDFLARE_EMAIL`,
  and `CLOUDFLARE_ACCOUNT_ID` in the environment.
- `deploy_backend.sh` deploys `server/` over SSH. It rsyncs the code into a
  staging dir (`$APP.next`, tests excluded), runs `uv sync` and the
  preflight there with the real env file — `import config`, a missing
  `CONTACT_EMAIL` only warns (the legal pages then show the derived
  `support@<BASE_URL host>` address), and a console-script spawn proves the
  venv runs. A failure there aborts before the live dir is touched. Then
  the live code is snapshotted to `$APP.prev` — staged as `$APP.prev.tmp`,
  marked complete, and promoted atomically — and the staged code is
  rsynced into `$APP` excluding `.venv` (a built venv is never moved, so
  its absolute-path shebangs stay valid). A failed snapshot aborts the
  deploy with the live tree untouched. After the swap, `uv sync` runs in
  `$APP` before the same preflight, `alembic upgrade head`, a restart, and
  a `/healthz` check that retries up to `HEALTH_TIMEOUT` times (default 30),
  one second apart; each attempt is capped at 3 seconds, so a server that
  accepts connections but never answers costs at most about four times
  `HEALTH_TIMEOUT` seconds. A failed post-swap step restores the previous code
  and restarts — but only when the completeness marker proves the snapshot
  is whole, otherwise it reports `ROLLBACK NOT POSSIBLE` and touches
  nothing; a rollback that cannot finish reports `ROLLBACK FAILED` instead
  of claiming success. The staged venv in `$APP.next` is dropped once the
  deploy succeeds. The database is snapshotted first via `BACKUP_CMD`
  (default `/usr/local/bin/shipswipe-backup.sh`) — `SKIP_BACKUP=1` is the
  only way to skip that step. Set `SHIPSWIPE_HOST` and optionally
  `APP_DIR`, `ENV_FILE`, `SERVICE`, `HEALTHCHECK_URL`, and
  `HEALTH_TIMEOUT`. A deploy holds a lock directory (`$APP.deploy.lock`) on
  the box so two deploys cannot overlap; if a crashed deploy leaves it
  behind, remove it with `ssh <host> rmdir <APP_DIR>.deploy.lock` once
  nothing is running. Run `scripts/test_deploy_backend.sh` to simulate the
  whole flow offline after changing the script.

The backend runs behind a proxy or tunnel that terminates TLS and sets the
client IP header (see Security notes). The production service is expected
to serve `main:bootstrap` with `uv run stario serve`, passing
`--max-request-body-bytes 65536` in the unit's ExecStart: the app's own
64 KB parse cap only runs after a chunked body is already buffered, so the
transport cap is what actually bounds per-request memory.

## Security notes

- No Content-Security-Policy is set. Datastar drives the UI through
  inline expressions and eval-adjacent attributes, so a CSP would either
  break the app or be wide open anyway. The other baseline headers
  (`X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`) are set.
- The origin must only be reachable through the tunnel or proxy that sets
  `cf-connecting-ip`. The login rate limiter trusts that header, so direct
  public access to the origin would let clients spoof it.
- Every state-changing POST is checked against `BASE_URL`: a
  `Sec-Fetch-Site` other than `same-origin`/`none`, or an `Origin` header
  that isn't BASE_URL's scheme+host+port, gets a 403 before anything is
  written — `SameSite=Lax` alone still let a sibling subdomain ride the
  session cookie, since same-site is not same-origin. Requests carrying
  neither header pass, and an explicit default port (`:443` or `:80`) in
  `BASE_URL` counts as no port.
- Request bodies are capped at 64 KB (larger gets a 413) and form bodies
  at 100 fields, so a flood body cannot stall the event loop on parsing.
- Run production with `APP_ENV=production` and a `MAGIC_LINK_SECRET` of at
  least 32 characters. The app refuses to boot outside dev/test with a
  missing, default, or short secret.
- Magic links are single-use and expire quickly; sessions live in Redis
  for 30 days.

## License

MIT. See [LICENSE](LICENSE). Vendored third-party code is listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
