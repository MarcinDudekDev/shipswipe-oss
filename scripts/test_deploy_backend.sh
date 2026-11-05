#!/usr/bin/env bash
# Offline simulation harness for deploy_backend.sh — no real host is touched.
#
# The "remote box" is a scratch dir: APP_DIR/ENV_FILE/BACKUP_CMD point inside
# it, and PATH shims translate the script's remote operations:
#   ssh <box> "<cmd>"  -> bash -c "<cmd>"        (remote command == local bash)
#   rsync ... box:path -> real rsync ... path    (host: prefix stripped)
#   systemctl / curl   -> appended to calls.log
#   sleep              -> no-op
# ~/.local/bin/uv (inside a fake HOME) emulates just enough of uv:
#   uv sync -> builds .venv/bin/{python,alembic}; the alembic shebang carries
#              the ABSOLUTE path it was built at, exactly like a real uv venv —
#              so a deploy that renames a built venv is caught by the harness
#              the same way prod was.
#   uv run X -> exec X with $PWD/.venv/bin first on PATH
#
# Scenarios asserted:
#   happy path          — new code live, venv shebangs point at $APP (not
#                         $APP.next), alembic ran, restart + healthcheck ran,
#                         CONTACT_EMAIL warning printed, DB snapshot taken,
#                         live snapshot marked complete, staged venv dropped.
#   preflight failure   — deploy aborts BEFORE the live dir is touched.
#   alembic failure     — rollback restores the old code and restarts.
#   snapshot failure    — a half-written $APP.prev.tmp aborts the deploy with
#                         live code byte-identical and no rollback claimed.
#   slow healthcheck    — a service that answers only after a few seconds is
#                         not rolled back.
#   hung healthcheck    — a listener that accepts but never replies: every
#                         curl is bounded by --max-time, the deploy fails in
#                         finite time and rolls back.
#   rollback failure    — a failed restart inside rollback is reported as
#                         "ROLLBACK FAILED" (exit 2), never "rolled back".
#   first-deploy swap   — with no complete snapshot, rollback refuses to
#                         --delete ( "ROLLBACK NOT POSSIBLE", exit 2 ).
#   concurrent deploy   — a second deploy while one is running is refused by
#                         the deploy lock, before it touches anything.
#   signal mid-swap     — SIGTERM while $APP may hold mixed code runs the same
#                         rollback a failed step would (the trap covers
#                         INT/TERM; a lone-PID SIGINT doesn't exercise it in
#                         the sim the way a real Ctrl-C does — bash defers it
#                         unless the foreground child dies of INT too).
#
# Run: bash scripts/test_deploy_backend.sh   (exit 0 = all checks passed)
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEPLOY="${DEPLOY_UNDER_TEST:-$REPO_ROOT/deploy_backend.sh}"
REAL_RSYNC="$(command -v rsync)"
REAL_PYTHON3="$(command -v python3)"
PASS=0
FAIL=0

check() { # <name> <command...> — PASS when the command exits 0
  local name="$1"; shift
  if "$@" >/dev/null 2>&1; then
    PASS=$((PASS + 1)); echo "PASS  $name"
  else
    FAIL=$((FAIL + 1)); echo "FAIL  $name"
  fi
}

check_file_contains() { grep -qF "$2" "$1"; }
check_file_not_contains() { ! grep -qF "$2" "$1"; }
check_eq() { [ "$1" = "$2" ]; }
check_not_exists() { [ ! -e "$1" ]; }
check_exists() { [ -e "$1" ]; }

make_shims() {
  # $1 = shim bin dir, $2 = fake home dir
  mkdir -p "$1" "$2/.local/bin" "$(dirname "$SIM_LOG")"

  cat > "$1/ssh" <<'EOF'
#!/usr/bin/env bash
# ssh shim: "<host> <command>" -> run the command in local bash.
shift
exec bash -c "$1"
EOF

  cat > "$1/rsync" <<EOF
#!/usr/bin/env bash
# rsync shim: drop "-e ssh" and strip "host:" prefixes, then the real rsync.
args=()
skip=0
for a in "\$@"; do
  if [ "\$skip" = 1 ]; then skip=0; continue; fi
  case "\$a" in
    -e) skip=1 ;;
    *:/*) args+=("\${a#*:}") ;;
    *) args+=("\$a") ;;
  esac
done
# Sabotage hook: when RSYNC_SABOTAGE_MATCH is set and the destination arg
# contains it, land only part of the tree and die like a mid-transfer
# failure (disk full, dropped connection) — the deploy must treat the copy
# as failed even though files did arrive.
if [ -n "\${RSYNC_SABOTAGE_MATCH:-}" ]; then
  last=\$(( \${#args[@]} - 1 ))
  case "\${args[\$last]}" in
    *"\$RSYNC_SABOTAGE_MATCH"*)
      dst="\${args[\$last]}"
      src="\${args[\$(( last - 1 ))]}"
      mkdir -p "\$dst"
      [ -f "\$src/CODE_VERSION" ] && cp "\$src/CODE_VERSION" "\$dst/"
      echo "rsync: write failed: No space left on device (28)" >&2
      exit 11
      ;;
  esac
fi
exec "$REAL_RSYNC" "\${args[@]}"
EOF

  cat > "$1/systemctl" <<'EOF'
#!/usr/bin/env bash
echo "systemctl $*" >> "$SIM_LOG"
exit "${SYSTEMCTL_FAIL:-0}"
EOF

  cat > "$1/curl" <<'EOF'
#!/usr/bin/env bash
# curl shim: logs the call and answers healthy — unless CURL_FAIL=1 or the
# call count (kept in a side file) is still <= CURL_FAIL_FIRST, which fakes a
# service that takes a few seconds to come up. CURL_HANG_FIRST=N instead
# fakes a listener that accepts but never replies for the first N calls: a
# real curl is only rescued by --max-time, so the shim honours it (sleeps
# that many seconds, exits 28) — and emulates a long unbounded hang without
# it (still finite, so a regression costs seconds, not forever).
echo "curl $*" >> "$SIM_LOG"
n=0
[ -f "$SIM_LOG.curl-n" ] && n=$(cat "$SIM_LOG.curl-n")
n=$((n + 1))
echo "$n" > "$SIM_LOG.curl-n"
if [ "${CURL_HANG_FIRST:-0}" -ge "$n" ]; then
  max_time=""
  prev=""
  for a in "$@"; do
    if [ "$prev" = "--max-time" ]; then max_time="$a"; fi
    prev="$a"
  done
  if [ -n "$max_time" ]; then
    /bin/sleep "$max_time"
  else
    /bin/sleep "${CURL_HANG_UNBOUNDED:-20}"
  fi
  exit 28
fi
# CURL_OK_DELAY=N slows a healthy answer by N real seconds — used to hold a
# succeeding healthcheck in flight long enough to signal the deploy mid-poll.
[ "${CURL_OK_DELAY:-0}" != "0" ] && /bin/sleep "$CURL_OK_DELAY"
echo "ok"
if [ "${CURL_FAIL_FIRST:-0}" -ge "$n" ]; then exit 1; fi
exit "${CURL_FAIL:-0}"
EOF

  cat > "$1/sleep" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF

  cat > "$2/.local/bin/uv" <<EOF
#!/usr/bin/env bash
# uv shim: "uv sync" builds a fake venv whose console script has the absolute
# build path in its shebang (real uv venv behaviour); "uv run" uses it.
cmd="\$1"; shift
case "\$cmd" in
  sync)
    # Real uv-sync does NOT rewrite an already-satisfied venv — which is
    # exactly why a moved venv keeps stale shebangs. Same here: existing
    # .venv means "Audited N packages", not a rebuild.
    if [ -d .venv/bin ]; then
      echo "Audited 1 package"
      exit 0
    fi
    mkdir -p .venv/bin
    ln -sf "$REAL_PYTHON3" .venv/bin/python
    cat > .venv/bin/alembic <<'PYEOF'
import os
import sys
if "--help" in sys.argv:
    sys.exit(0)
if sys.argv[1:] == ["upgrade", "head"]:
    with open(os.path.join(os.environ["SIM_REMOTE"], "alembic.log"), "a") as f:
        f.write("upgrade head\n")
    sys.exit(int(os.environ.get("ALEMBIC_FAIL", "0")))
sys.exit(0)
PYEOF
    # Rewrite the shebang to the absolute build path, like a real uv venv.
    printf '#!%s/.venv/bin/python\n' "\$PWD" | cat - .venv/bin/alembic > .venv/bin/.alembic.new
    mv .venv/bin/.alembic.new .venv/bin/alembic
    chmod +x .venv/bin/alembic
    ;;
  run)
    PATH="\$PWD/.venv/bin:\$PATH" exec "\$@"
    ;;
  *)
    echo "uv shim: unsupported subcommand \$cmd" >&2
    exit 2
    ;;
esac
EOF

  chmod +x "$1/ssh" "$1/rsync" "$1/systemctl" "$1/curl" "$1/sleep" "$2/.local/bin/uv"
}

setup_sandbox() {
  # $1 = scenario dir, $2 = "noapp" to simulate a first deploy (no live dir);
  # builds remote fs, fake repo (deploy script + fake server/ code at version
  # "new-code"), and a live $APP at version "old-code".
  local T="$1"
  SIM_REMOTE="$T/remote"
  SIM_LOG="$T/calls.log"
  export SIM_REMOTE SIM_LOG
  mkdir -p "$T/repo/server" "$SIM_REMOTE/backups" "$T/bin" "$T/home"

  make_shims "$T/bin" "$T/home"

  cp "$DEPLOY" "$T/repo/deploy_backend.sh"

  # The code tree the deploy ships (stands in for server/).
  cat > "$T/repo/server/config.py" <<'EOF'
"""Fake config for the deploy simulation."""
import os
if os.environ.get("PREFLIGHT_FAIL"):
    raise RuntimeError("config preflight failed")
settings = type("S", (), {"contact_email": "support@app.example"})()
EOF
  # The size difference matters: same-size same-second files would be
  # skipped by rsync's quick check and the swap checks below could pass
  # vacuously.
  echo "new-code-ROUND4" > "$T/repo/server/CODE_VERSION"
  echo '[project]
name = "fake"
version = "0.1.0"' > "$T/repo/server/pyproject.toml"

  # The live dir: old code + an already-built venv (via the same uv shim).
  # "noapp" skips it: a first deploy has nothing live to snapshot.
  local app="$SIM_REMOTE/app"
  if [ "${2:-}" != "noapp" ]; then
    mkdir -p "$app"
    echo "old-code" > "$app/CODE_VERSION"
    ( cd "$app" && HOME="$T/home" "$T/home/.local/bin/uv" sync )
  fi

  # Remote env file + backup command.
  cat > "$SIM_REMOTE/shipswipe.env" <<EOF
BASE_URL=https://app.example
$EXTRA_ENV_FILE
EOF
  cat > "$SIM_REMOTE/backup.sh" <<'EOF'
#!/usr/bin/env bash
touch "$SIM_REMOTE/backups/predeploy-$$.dump"
EOF
  chmod +x "$SIM_REMOTE/backup.sh"
}

run_deploy() {
  # Runs the deploy inside the sandbox; stdout+stderr -> $DEPLOY_OUT, rc -> $RC.
  local T="$1"; shift
  DEPLOY_OUT="$T/deploy.out"
  env \
    HOME="$T/home" \
    PATH="$T/bin:$PATH" \
    SIM_REMOTE="$SIM_REMOTE" \
    SIM_LOG="$SIM_LOG" \
    SHIPSWIPE_HOST=fakebox \
    APP_DIR="$SIM_REMOTE/app" \
    ENV_FILE="$SIM_REMOTE/shipswipe.env" \
    SERVICE=shipswipe \
    BACKUP_CMD="$SIM_REMOTE/backup.sh" \
    BACKUP_DIR="$SIM_REMOTE/backups" \
    SKIP_TESTS=1 \
    "$@" \
    bash "$T/repo/deploy_backend.sh" > "$DEPLOY_OUT" 2>&1
  RC=$?
}

scenario_happy() {
  local T="$SCRATCH/happy"
  EXTRA_ENV_FILE="" setup_sandbox "$T"
  run_deploy "$T"

  check "happy: deploy exits 0" check_eq "$RC" 0
  check "happy: live dir has new code" check_file_contains "$SIM_REMOTE/app/CODE_VERSION" "new-code"
  check "happy: staged venv never entered live dir" check_file_contains "$SIM_REMOTE/app/.venv/bin/alembic" "$SIM_REMOTE/app/.venv/bin/python"
  check "happy: live venv shebang is self-referential" bash -c "head -1 '$SIM_REMOTE/app/.venv/bin/alembic' | grep -qF '#!$SIM_REMOTE/app/.venv/bin/python'"
  check "happy: staging venv did not leak into live dir" bash -c "! grep -qsF '$SIM_REMOTE/app.next' '$SIM_REMOTE/app/.venv/bin/alembic'"
  check "happy: live alembic console script runs" bash -c "'$SIM_REMOTE/app/.venv/bin/alembic' --help >/dev/null"
  check "happy: alembic upgrade head ran" check_file_contains "$SIM_REMOTE/alembic.log" "upgrade head"
  check "happy: service restarted" check_file_contains "$SIM_LOG" "systemctl restart shipswipe"
  check "happy: healthcheck curled" check_file_contains "$SIM_LOG" "curl -fsS --connect-timeout 2 --max-time 3 localhost:8787/healthz"
  check "happy: no rollback ran" check_file_not_contains "$DEPLOY_OUT" "rolled back"
  check "happy: CONTACT_EMAIL warning printed" check_file_contains "$DEPLOY_OUT" "WARNING: CONTACT_EMAIL is not set"
  check "happy: warning names the default address" check_file_contains "$DEPLOY_OUT" "support@app.example"
  check "happy: DB snapshot taken" bash -c "ls '$SIM_REMOTE/backups'/*.dump >/dev/null 2>&1"
  check "happy: prev snapshot has old code" check_file_contains "$SIM_REMOTE/app.prev/CODE_VERSION" "old-code"
  check "happy: prev snapshot is marked complete" check_exists "$SIM_REMOTE/app.prev/.snapshot-complete"
  check "happy: snapshot marker not copied into live" check_not_exists "$SIM_REMOTE/app/.snapshot-complete"
  check "happy: staged venv removed after deploy" check_not_exists "$SIM_REMOTE/app.next/.venv"
  check "happy: staged code kept after deploy" check_exists "$SIM_REMOTE/app.next/CODE_VERSION"
}

scenario_preflight_fail() {
  local T="$SCRATCH/preflight"
  EXTRA_ENV_FILE="PREFLIGHT_FAIL=1" setup_sandbox "$T"
  run_deploy "$T"

  check "preflight: deploy exits non-zero" bash -c "[ $RC -ne 0 ]"
  check "preflight: live code untouched" check_file_contains "$SIM_REMOTE/app/CODE_VERSION" "old-code"
  check "preflight: live venv still works" bash -c "'$SIM_REMOTE/app/.venv/bin/alembic' --help >/dev/null"
  check "preflight: no restart issued" check_not_exists "$SIM_LOG"
  check "preflight: no alembic run" check_not_exists "$SIM_REMOTE/alembic.log"
  check "preflight: no live snapshot was needed" check_not_exists "$SIM_REMOTE/app.prev"
}

scenario_alembic_fail() {
  local T="$SCRATCH/alembic"
  EXTRA_ENV_FILE="" setup_sandbox "$T"
  run_deploy "$T" ALEMBIC_FAIL=1

  check "alembic: deploy exits non-zero" bash -c "[ $RC -ne 0 ]"
  check "alembic: rollback restored old code" check_file_contains "$SIM_REMOTE/app/CODE_VERSION" "old-code"
  check "alembic: rollback restarted the service" check_file_contains "$SIM_LOG" "systemctl restart shipswipe"
  check "alembic: rollback message printed" check_file_contains "$DEPLOY_OUT" "rolled back"
  check "alembic: rollback verified health first" check_file_contains "$SIM_LOG" "curl"
  check "alembic: deploy healthcheck step never ran" check_file_not_contains "$DEPLOY_OUT" "==> 10/10"
  check "alembic: live venv still works after rollback" bash -c "'$SIM_REMOTE/app/.venv/bin/alembic' --help >/dev/null"
}

scenario_snapshot_fail() {
  # The live-code snapshot lands only part of the tree then dies (disk full,
  # dropped ssh): the deploy must abort with the live tree byte-identical —
  # and must NOT try to roll back, since nothing live was ever touched.
  local T="$SCRATCH/snapshot-fail"
  EXTRA_ENV_FILE="" setup_sandbox "$T"
  local before after
  before=$(cd "$SIM_REMOTE/app" && find . -type f -exec shasum -a 256 {} + | sort -k2)
  run_deploy "$T" RSYNC_SABOTAGE_MATCH="app.prev.tmp"
  after=$(cd "$SIM_REMOTE/app" && find . -type f -exec shasum -a 256 {} + | sort -k2)

  check "snapshot-fail: deploy exits non-zero" bash -c "[ $RC -ne 0 ]"
  check "snapshot-fail: live code byte-identical" check_eq "$before" "$after"
  check "snapshot-fail: no restart issued" bash -c "! grep -qs 'systemctl' '$SIM_LOG'"
  check "snapshot-fail: no rollback claimed" check_file_not_contains "$DEPLOY_OUT" "rolled back"
  check "snapshot-fail: partial snapshot not promoted" check_not_exists "$SIM_REMOTE/app.prev"
}

scenario_slow_health() {
  # A service that only answers healthy after a few seconds is NOT rolled
  # back: the healthcheck retries until HEALTH_TIMEOUT instead of failing
  # on the first refused curl.
  local T="$SCRATCH/slow-health"
  EXTRA_ENV_FILE="" setup_sandbox "$T"
  run_deploy "$T" CURL_FAIL_FIRST=4

  check "slow-health: deploy exits 0" check_eq "$RC" 0
  check "slow-health: live dir has new code" check_file_contains "$SIM_REMOTE/app/CODE_VERSION" "new-code"
  check "slow-health: healthcheck retried past 4 failures" bash -c "[ \$(cat '$SIM_LOG.curl-n') -gt 4 ]"
  check "slow-health: no rollback ran" check_file_not_contains "$DEPLOY_OUT" "rolled back"
}

scenario_rollback_restart_fail() {
  # A rollback whose own restart fails must not claim success: the restore
  # ran, but the service is down — "ROLLBACK FAILED" and exit 2, not
  # "rolled back".
  local T="$SCRATCH/rollback-fail"
  EXTRA_ENV_FILE="" setup_sandbox "$T"
  run_deploy "$T" ALEMBIC_FAIL=1 SYSTEMCTL_FAIL=1

  check "rollback-fail: exit code is 2" check_eq "$RC" 2
  check "rollback-fail: prints ROLLBACK FAILED" check_file_contains "$DEPLOY_OUT" "ROLLBACK FAILED"
  check "rollback-fail: does not claim rolled back" check_file_not_contains "$DEPLOY_OUT" "rolled back"
  check "rollback-fail: code restore still ran" check_file_contains "$SIM_REMOTE/app/CODE_VERSION" "old-code"
}

scenario_first_deploy_swap_fail() {
  # First deploy, swap rsync dies midway: there is no previous version, so
  # rollback must refuse (no marker) instead of "restoring" an empty or
  # partial tree.
  local T="$SCRATCH/first-deploy-swap-fail"
  EXTRA_ENV_FILE="" setup_sandbox "$T" noapp
  run_deploy "$T" RSYNC_SABOTAGE_MATCH="$SIM_REMOTE/app/"

  check "swap-fail: exit code is 2" check_eq "$RC" 2
  check "swap-fail: prints ROLLBACK NOT POSSIBLE" check_file_contains "$DEPLOY_OUT" "ROLLBACK NOT POSSIBLE"
  check "swap-fail: does not claim rolled back" check_file_not_contains "$DEPLOY_OUT" "rolled back"
  check "swap-fail: no restart issued" bash -c "! grep -qs 'systemctl restart' '$SIM_LOG'"
}

scenario_hung_healthcheck() {
  # A listener that accepts but never replies would hang an unbounded curl
  # forever, making HEALTH_TIMEOUT a lie — the post-swap deploy would sit
  # dead with no rollback. With --max-time the polls fail in bounded time
  # and the deploy rolls back. The hang only covers the deploy's own polls
  # (CURL_HANG_FIRST=3 at 1 poll/second), so the rollback's healthcheck sees
  # the service answering again and reports a clean rollback.
  local T="$SCRATCH/hung-health"
  EXTRA_ENV_FILE="" setup_sandbox "$T"
  local started=$SECONDS
  run_deploy "$T" CURL_HANG_FIRST=3 HEALTH_TIMEOUT=3
  local elapsed=$((SECONDS - started))

  check "hung-health: deploy exits non-zero" bash -c "[ $RC -ne 0 ]"
  check "hung-health: rollback ran" check_file_contains "$DEPLOY_OUT" "rolled back"
  check "hung-health: deploy bounded, no curl hang" bash -c "[ $elapsed -lt 30 ]"
  check "hung-health: every curl carried a timeout" \
    bash -c "! grep -s '^curl ' '$SIM_LOG' | grep -v -- '--max-time' | grep -q ."
  check "hung-health: old code restored" check_file_contains "$SIM_REMOTE/app/CODE_VERSION" "old-code"
  check "hung-health: lock released" check_not_exists "$SIM_REMOTE/app.deploy.lock"
}

scenario_concurrent_deploy() {
  # Two deploys share $APP.next/$APP.prev state on the box — the second must
  # be refused by the deploy lock, before it touches anything. The first
  # deploy is held in flight by a slow remote backup command, so it still
  # owns the lock when the second one tries to take it.
  local T="$SCRATCH/concurrent"
  EXTRA_ENV_FILE="" setup_sandbox "$T"
  cat > "$SIM_REMOTE/backup.sh" <<'EOF'
#!/usr/bin/env bash
/bin/sleep 2
touch "$SIM_REMOTE/backups/predeploy-$$.dump"
EOF
  chmod +x "$SIM_REMOTE/backup.sh"

  env \
    HOME="$T/home" \
    PATH="$T/bin:$PATH" \
    SIM_REMOTE="$SIM_REMOTE" \
    SIM_LOG="$SIM_LOG" \
    SHIPSWIPE_HOST=fakebox \
    APP_DIR="$SIM_REMOTE/app" \
    ENV_FILE="$SIM_REMOTE/shipswipe.env" \
    SERVICE=shipswipe \
    BACKUP_CMD="$SIM_REMOTE/backup.sh" \
    BACKUP_DIR="$SIM_REMOTE/backups" \
    SKIP_TESTS=1 \
    bash "$T/repo/deploy_backend.sh" > "$T/first.out" 2>&1 &
  local first_pid=$!
  # Wait until the first deploy actually holds the lock (it sits in the
  # 2-second backup right after taking it) — never start the second run on
  # a guess about timing.
  local i
  for i in $(seq 100); do
    [ -d "$SIM_REMOTE/app.deploy.lock" ] && break
    /bin/sleep 0.1
  done
  run_deploy "$T"
  local second_rc=$RC
  wait "$first_pid"
  local first_rc=$?

  check "concurrent: first deploy exits 0" check_eq "$first_rc" 0
  check "concurrent: overlapping deploy refused" bash -c "[ $second_rc -ne 0 ]"
  check "concurrent: refusal names the deploy lock" check_file_contains "$DEPLOY_OUT" "deploy lock"
  check "concurrent: refusal is pre-change" check_file_not_contains "$DEPLOY_OUT" "==> 7/10"
  check "concurrent: first deploy still landed" check_file_contains "$SIM_REMOTE/app/CODE_VERSION" "new-code"
  check "concurrent: lock released after deploy" check_not_exists "$SIM_REMOTE/app.deploy.lock"
}

scenario_sigterm_during_healthcheck() {
  # Killing the local script while $APP may hold mixed code must not leave
  # it that way: the swap-window trap routes the signal through rollback.
  # A healthy-but-slow healthcheck keeps the window open long enough to
  # signal into: the poll itself succeeds (no `|| rollback` fires), then the
  # pending trap runs the rollback — ending with old code live and healthy.
  # TERM, not INT: bash only runs an INT trap if the foreground child died
  # of INT too (a real Ctrl-C hits the whole group); a lone-PID INT would be
  # deferred past the next command and lost. Same trap, same code path.
  local T="$SCRATCH/sigterm"
  EXTRA_ENV_FILE="" setup_sandbox "$T"
  env \
    HOME="$T/home" \
    PATH="$T/bin:$PATH" \
    SIM_REMOTE="$SIM_REMOTE" \
    SIM_LOG="$SIM_LOG" \
    SHIPSWIPE_HOST=fakebox \
    APP_DIR="$SIM_REMOTE/app" \
    ENV_FILE="$SIM_REMOTE/shipswipe.env" \
    SERVICE=shipswipe \
    BACKUP_CMD="$SIM_REMOTE/backup.sh" \
    BACKUP_DIR="$SIM_REMOTE/backups" \
    SKIP_TESTS=1 \
    CURL_OK_DELAY=2 \
    bash "$T/repo/deploy_backend.sh" > "$T/deploy.out" 2>&1 &
  local pid=$!
  # The first logged curl means step 10 — inside the swap window — is live.
  local i
  for i in $(seq 150); do
    grep -qs "^curl " "$SIM_LOG" 2>/dev/null && break
    /bin/sleep 0.1
  done
  kill -TERM "$pid"
  wait "$pid"
  local rc=$?

  check "sigterm: deploy exits non-zero" bash -c "[ $rc -ne 0 ]"
  check "sigterm: interrupt named as the failed step" check_file_contains "$T/deploy.out" "interrupted by signal"
  check "sigterm: rollback attempted on interrupt" check_file_contains "$T/deploy.out" "attempting rollback"
  check "sigterm: rolled back to healthy old code" check_file_contains "$T/deploy.out" "rolled back"
  check "sigterm: old code restored" check_file_contains "$SIM_REMOTE/app/CODE_VERSION" "old-code"
  check "sigterm: lock released" check_not_exists "$SIM_REMOTE/app.deploy.lock"
}

SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/deploysim.XXXXXX")"
# Canonical path: a trailing slash in TMPDIR or a /var -> /private/var symlink
# would otherwise make the shebang comparisons below miss.
SCRATCH="$(cd "$SCRATCH" && pwd -P)"
if [ "${KEEP:-0}" = "1" ]; then
  echo "scratch kept at $SCRATCH"
else
  trap 'rm -rf "$SCRATCH"' EXIT
fi

scenario_happy
scenario_preflight_fail
scenario_alembic_fail
scenario_snapshot_fail
scenario_slow_health
scenario_rollback_restart_fail
scenario_first_deploy_swap_fail
scenario_hung_healthcheck
scenario_concurrent_deploy
scenario_sigterm_during_healthcheck

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
