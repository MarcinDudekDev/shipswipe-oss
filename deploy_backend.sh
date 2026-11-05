#!/usr/bin/env bash
# Deploy the ShipSwipe Stario BACKEND (server/) to a remote host over SSH.
#
# GUARDRAILS:
#   - Snapshots the prod Postgres DB first unless SKIP_BACKUP=1 is passed.
#     If the backup command is missing on the box, the deploy aborts.
#   - Ships CODE ONLY. The DB is a separate Postgres instance and is never rsynced/dropped.
#   - Excludes tests/ so no drop_all/create_all code ever lands on the prod box.
#   - Ships into a staging dir ($APP.next), runs uv sync and the `import config`
#     + console-script preflight there with the real env file. A bad env or
#     lockfile aborts before the live tree is touched.
#   - NEVER renames a directory that holds a built .venv: uv console-script
#     shebangs carry the absolute path they were built at, so a moved venv is
#     a broken venv. Staged code is rsynced into $APP (excluding .venv) and
#     the live venv is re-synced at its own, unchanged path.
#   - Snapshots the live code (no venv) into $APP.prev BEFORE the swap, staged
#     as $APP.prev.tmp and promoted atomically with a completeness marker.
#     The snapshot step is deliberately not protected by rollback: nothing
#     live has changed yet, so a failed snapshot simply aborts the deploy.
#     A failed post-swap step (sync, preflight, alembic, restart, healthcheck)
#     auto-restores the previous code into $APP and restarts the service —
#     but only when the marker proves the snapshot is complete.
#   - Runs `alembic upgrade head` after the swap, before restart (env: $ENV_FILE).
#   - Restarts the service and polls the healthcheck every second for up to
#     HEALTH_TIMEOUT seconds before declaring failure. Each curl is bounded
#     (--connect-timeout/--max-time) so a listener that accepts but never
#     answers can't hang the deploy past its own timeout.
#   - Takes a deploy lock ($APP.deploy.lock, an atomic remote mkdir) so two
#     deploys can't overlap on the shared $NEXT/$PREV state. Released on
#     every exit path; a crashed deploy leaves it behind — remove it by hand
#     (`ssh <box> rmdir $APP.deploy.lock`) once nothing is running.
#   - Traps SIGINT/SIGTERM during the swap window (steps 7-10): an interrupt
#     while $APP may hold mixed code runs the same rollback a failure would.
#
# Required env:
#   SHIPSWIPE_HOST  ssh target — a host or an alias from ~/.ssh/config.
# Optional env:
#   APP_DIR         deploy root on the box      (default /opt/shipswipe)
#   ENV_FILE        env file sourced by alembic (default /etc/shipswipe.env)
#   SERVICE         systemd unit name           (default shipswipe)
#   BACKUP_CMD      remote pre-deploy DB snapshot command; may carry arguments —
#                   only its first word is probed with command -v
#                   (default /usr/local/bin/shipswipe-backup.sh)
#   BACKUP_DIR      remote dir of *.dump files listed at the end (default /var/backups/shipswipe)
#   HEALTHCHECK_URL checked on the box          (default localhost:8787/healthz)
#   HEALTH_TIMEOUT  seconds to wait for the healthcheck (default 30)
#   SKIP_TESTS=1    bypass the local test gate
#   SKIP_BACKUP=1   deploy WITHOUT a DB snapshot (the only way to skip it)
#
# Ops note: the systemd unit lives on the box, not in this repo. Its
# ExecStart should pass `--max-request-body-bytes 65536` to `stario serve`
# so oversized request bodies are refused before they are buffered into
# memory — see README -> Deployment.
#
# The static marketing site is a DIFFERENT target — use ./deploy.sh (Cloudflare Pages).
set -euo pipefail
cd "$(dirname "$0")"

if [ -z "${SHIPSWIPE_HOST:-}" ]; then
  echo "usage: SHIPSWIPE_HOST=<ssh-host> [APP_DIR=/opt/shipswipe] [SKIP_BACKUP=1] $0" >&2
  exit 1
fi
BOX="$SHIPSWIPE_HOST"
APP="${APP_DIR:-/opt/shipswipe}"
NEXT="$APP.next"
PREV="$APP.prev"
ENV_FILE="${ENV_FILE:-/etc/shipswipe.env}"
SERVICE="${SERVICE:-shipswipe}"
BACKUP_CMD="${BACKUP_CMD:-/usr/local/bin/shipswipe-backup.sh}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/shipswipe}"
HEALTHCHECK_URL="${HEALTHCHECK_URL:-localhost:8787/healthz}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-30}"
UV="~/.local/bin/uv"
LOCK="$APP.deploy.lock"

# Deploy lock, taken before anything else touches the box: two overlapping
# deploys would share $NEXT and $PREV and clobber each other's snapshots.
# mkdir is atomic — the loser refuses instead of interleaving. Probe the
# outcome explicitly so an unreachable box isn't misreported as a held lock.
if ! lock_state=$(ssh "$BOX" "mkdir $LOCK 2>/dev/null && echo acquired || echo held"); then
  echo "!! cannot reach $BOX to take the deploy lock — aborting before any changes" >&2
  exit 1
fi
# Match on the last line only: a login shell that prints a banner must not turn
# a lock we just took into a "held" lock that then blocks every later deploy.
lock_state=$(printf '%s\n' "$lock_state" | tail -n1)
if [ "$lock_state" != "acquired" ] && [ "$lock_state" != "held" ]; then
  echo "!! unexpected answer while taking the deploy lock: $lock_state — aborting" >&2
  echo "   (check: ssh $BOX ls -d $LOCK)" >&2
  exit 1
fi
if [ "$lock_state" != "acquired" ]; then
  echo "!! deploy lock $LOCK already exists on $BOX — another deploy is running" >&2
  echo "   (or a crashed one left it: ssh $BOX rmdir $LOCK) — aborting" >&2
  exit 1
fi
LOCK_HELD=1
# Release on every exit path — success, pre-swap abort, or rollback's exit.
trap 'if [ "${LOCK_HELD:-0}" = "1" ]; then ssh "$BOX" "rmdir $LOCK" >/dev/null 2>&1 || true; fi' EXIT
# TERM/HUP (CI cancel, closed terminal) skip the EXIT trap unless we exit on them.
trap 'exit 130' INT TERM HUP

# Preflight run inside a candidate dir with the real env file sourced:
#   - `import config` must succeed — a bad env file kills the deploy here,
#     before the service restarts on a config it cannot boot with.
#   - `alembic --help` must spawn — a console script only runs when the venv
#     shebang points at a live interpreter, which is exactly what a moved
#     venv breaks; checking it here catches that whole class of failure.
preflight() {  # $1 = remote dir to preflight in
  ssh "$BOX" "cd $1 && set -a && . $ENV_FILE && set +a && $UV run python -c 'import config' && $UV run alembic --help >/dev/null"
}

# A missing CONTACT_EMAIL only warns: the legal pages then show the derived
# support@<BASE_URL host> address, which may not be a real mailbox. Checked
# once in staging — printing it again at the live preflight just repeats it.
warn_contact_email() {  # $1 = remote dir to check with the env file sourced
  ssh "$BOX" "cd $1 && set -a && . $ENV_FILE && set +a && $UV run python -c 'import config, os; os.environ.get(\"CONTACT_EMAIL\") or print(\"WARNING: CONTACT_EMAIL is not set in $ENV_FILE — legal pages will show the default \" + config.settings.contact_email)'"
}

# The service may need seconds to answer on a loaded box: poll once a second
# until HEALTH_TIMEOUT is exhausted before calling it dead — a slow boot is
# not a failed deploy. Gates step 10 and the rollback's "healthy" claim.
# Each curl is bounded: a listener that accepts but never answers (a stalled
# event loop on a loaded box) would otherwise hang every poll forever and
# HEALTH_TIMEOUT would stop being a bound — the deploy would sit post-swap
# with no rollback until the operator kills it.
healthcheck() {
  ssh "$BOX" "for i in \$(seq $HEALTH_TIMEOUT); do curl -fsS --connect-timeout 2 --max-time 3 $HEALTHCHECK_URL && exit 0; sleep 1; done; exit 1"
}

# Post-swap guard: once $APP holds new code, any failure restores the previous
# tree (code only — the venv never moved and still matches it) and restarts on
# the old code, then exits non-zero. Migrations already applied stay applied;
# the step-2 DB snapshot is the way back for schema.
rollback() {  # $1 = the step that failed
  # Already inside the failure path: a second Ctrl-C must not re-enter.
  trap - INT TERM
  echo "!! '$1' failed after the swap — attempting rollback from $PREV" >&2
  echo "!! alembic migrations already applied are NOT reverted — the pre-deploy DB snapshot is in $BACKUP_DIR" >&2
  # Only a COMPLETE snapshot may feed a --delete restore: a partial $PREV
  # would wipe live files it never copied, turning a failed deploy into an
  # outage. The marker is written by the snapshot step after its rsync and
  # promoted with the directory. Probe it explicitly — an unreachable box is
  # not "no snapshot", and neither failure lets us claim $APP is untouched.
  local probe
  if ! probe=$(ssh "$BOX" "test -f $PREV/.snapshot-complete && echo complete || echo missing"); then
    echo "!! ROLLBACK NOT POSSIBLE: cannot reach $BOX to check $PREV — state of $APP unknown, inspect it manually" >&2
    exit 2
  fi
  if [ "$probe" != "complete" ]; then
    echo "!! ROLLBACK NOT POSSIBLE: no complete snapshot at $PREV — $APP may hold mixed code, fix it manually" >&2
    exit 2
  fi
  if ssh "$BOX" "rsync -a --delete --exclude .venv --exclude .snapshot-complete $PREV/ $APP/ && cd $APP && $UV sync >/dev/null" \
    && ssh "$BOX" "systemctl restart $SERVICE" \
    && healthcheck; then
    echo "!! rolled back: $APP holds the previous code and $SERVICE is healthy" >&2
    exit 1
  fi
  echo "!! ROLLBACK FAILED — $APP may hold mixed code; manual action required" >&2
  exit 2
}

echo "==> 1/10 run local tests (gate) — set SKIP_TESTS=1 to bypass"
if [ "${SKIP_TESTS:-0}" != "1" ]; then
  ( cd server && uv run pytest -q )
fi

echo "==> 2/10 snapshot prod DB (pre-deploy backup) — set SKIP_BACKUP=1 to skip"
if [ "${SKIP_BACKUP:-0}" = "1" ]; then
  echo "    SKIP_BACKUP=1 — deploying WITHOUT a DB snapshot"
else
  if ! ssh "$BOX" "command -v ${BACKUP_CMD%% *} >/dev/null"; then
    echo "!! backup command $BACKUP_CMD not found on $BOX — aborting before any changes" >&2
    exit 1
  fi
  ssh "$BOX" "$BACKUP_CMD predeploy"
fi

echo "==> 3/10 rsync code into staging $NEXT (live tree untouched; tests excluded)"
ssh "$BOX" "mkdir -p $NEXT"
rsync -az --delete \
  --exclude .venv --exclude __pycache__ --exclude .pytest_cache \
  --exclude tests \
  -e ssh server/ "$BOX:$NEXT/"

echo "==> 4/10 uv sync deps (staging venv; its shebangs stay at $NEXT)"
ssh "$BOX" "cd $NEXT && $UV sync >/dev/null"

echo "==> 5/10 preflight in staging (import config + console script; env $ENV_FILE)"
preflight "$NEXT"
warn_contact_email "$NEXT"

echo "==> 6/10 snapshot live code to $PREV (staged as $PREV.tmp, promoted atomically)"
# Its own step, BEFORE $APP changes, and deliberately not under `|| rollback`:
# nothing live has been touched yet, so a failed snapshot must simply abort —
# rolling back here is what turns a partial copy into a wiped live tree.
# The marker proves the copy finished; rollback refuses to --delete without it.
ssh "$BOX" "rm -rf $PREV.tmp && mkdir -p $PREV.tmp && if [ -d $APP ]; then rsync -a --exclude .venv --exclude __pycache__ --exclude .pytest_cache --exclude .snapshot-complete $APP/ $PREV.tmp/ && touch $PREV.tmp/.snapshot-complete; fi && rm -rf $PREV && mv $PREV.tmp $PREV" \
  || { echo "!! live-code snapshot failed — aborting; $APP untouched" >&2; exit 1; }

echo "==> 7/10 rsync staged code into $APP (venv untouched)"
# From here $APP may hold mixed code, so an interrupt is no longer a clean
# abort: route Ctrl-C/TERM through the same rollback a failed step takes.
trap 'rollback "interrupted by signal"' INT TERM HUP
ssh "$BOX" "mkdir -p $APP && rsync -a --delete --exclude .venv --exclude __pycache__ --exclude .pytest_cache $NEXT/ $APP/" || rollback "code swap"

echo "==> 8/10 uv sync + preflight in $APP (live venv re-synced at its own path)"
ssh "$BOX" "cd $APP && $UV sync >/dev/null" || rollback "uv sync in $APP"
preflight "$APP" || rollback "live preflight"

echo "==> 9/10 alembic upgrade head (schema migrations; env from $ENV_FILE)"
ssh "$BOX" "cd $APP && set -a && . $ENV_FILE && set +a && $UV run alembic upgrade head" || rollback "alembic upgrade head"

echo "==> 10/10 restart service and healthcheck (up to ${HEALTH_TIMEOUT}s)"
ssh "$BOX" "systemctl restart $SERVICE" || rollback "service restart"
healthcheck || rollback "healthcheck"
trap - INT TERM

echo
echo "✔ backend deployed."
# The staged venv did its job (preflight); drop it so it stops holding disk —
# the staged code stays for reference. Cleanup never fails a finished deploy.
ssh "$BOX" "rm -rf $NEXT/.venv" || true
if [ "${SKIP_BACKUP:-0}" != "1" ]; then
  echo "Recent DB backups (newest first):"
  ssh "$BOX" "ls -1t $BACKUP_DIR/*.dump 2>/dev/null | head -3" || true
fi
