#!/bin/bash
# Test once: run the tests one at a time, and skip code that already passed.
#
# Run the tests, but only one run at a time, and not again for
# code that already passed. Use it as the TEST_CMD of the build and release
# scripts, so a build after a release doesn't test the same code twice.
#
# One at a time: a second run stops at once (exit 75) and says which is
# going. A run that died (a crash, a power cut) doesn't block the next one.
# Not again: after a pass it saves a fingerprint of every file git tracks or
# would track under WATCH, and of TEST_CMD. Same fingerprint, no run.
# A Runner template (`runner template copy test-once`). It's yours now:
# change the settings, or anything else, to suit this project.
#
#   scripts/test-once.sh           test, unless this code already passed
#   scripts/test-once.sh --force   test anyway
set -euo pipefail

# ---------------------------------------------------------------- settings
PROJECT_DIR=".."     # the project's folder, from this script's folder
PROJECT_NAME=""      # for notifications and the log folder; empty: the folder's name
TEST_CMD=""          # for example: pytest -q   (required)
WATCH=(".")          # the folders and files whose changes mean testing again
# ---------------------------------------------------------------- the rest
# Started from a Runner launcher there's no terminal, so each run's output
# also goes to a log (the last run only), and a notification says how it
# ended. SCRIPTS_QUIET=1 skips notifications and dialogs; a dialog then
# answers Cancel unless the script was given its answer as an option.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/$PROJECT_DIR" && pwd)"
cd "$ROOT"
PROJECT_NAME="${PROJECT_NAME:-$(basename "$ROOT")}"
SCRIPT="$(basename "${BASH_SOURCE[0]}" .sh)"
TITLE="$PROJECT_NAME $SCRIPT"
STEP="Starting"
if [ "$(uname)" = "Darwin" ]; then
  LOG_DIR="${SCRIPTS_LOG_DIR:-$HOME/Library/Logs/$PROJECT_NAME}"
else
  LOG_DIR="${SCRIPTS_LOG_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/$PROJECT_NAME/logs}"
fi
LOG="$LOG_DIR/$SCRIPT.log"
mkdir -p "$LOG_DIR"
: >"$LOG"
exec > >(tee -a "$LOG") 2>&1
echo "==> $TITLE, $(date '+%Y-%m-%d %H:%M:%S'), in $ROOT"

_quiet() { [ "${SCRIPTS_QUIET:-0}" = "1" ]; }
# AppleScript strings end at a double quote, so they become single quotes.
_as() { local text="$1"; printf '%s' "${text//\"/\'}"; }

notify() {
  _quiet && return 0
  if command -v osascript >/dev/null 2>&1; then
    osascript -e "display notification \"$(_as "$2")\" with title \"$(_as "$1")\"" >/dev/null 2>&1 || true
  elif command -v notify-send >/dev/null 2>&1; then
    notify-send "$1" "$2" >/dev/null 2>&1 || true
  fi
}

_on_failure() {
  local code=$?
  [ "$BASH_SUBSHELL" -eq 0 ] || return 0  # $(...) failures are reported where they're seen
  echo "ERROR: $STEP failed (exit $code)" >&2
  notify "$TITLE failed" "$STEP failed (exit $code). Log: ${LOG/#$HOME/~}"
}
set -o errtrace
trap _on_failure ERR

# fail MESSAGE: stop on purpose, saying why.
fail() { trap - ERR; echo "STOPPED: $1" >&2; notify "$TITLE stopped" "$1"; exit 1; }
# succeed MESSAGE: it worked.
succeed() { echo "==> $1"; notify "$TITLE" "$1"; }
# run NAME COMMAND: one of the commands from the settings.
run() { STEP="$1"; echo "==> $1: $2"; bash -c "$2"; }

# ---------------------------------------------------------------- the tests
[ -n "$TEST_CMD" ] || fail "TEST_CMD is empty. Set it at the top of $0."
force=0
[ "${1:-}" != "--force" ] || force=1

# Kept inside .git, which git never tracks.
STATE="$(git rev-parse --absolute-git-dir)/test-once"
mkdir -p "$STATE"

STEP="Taking the lock"
LOCK="$STATE/lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  holder="$(cat "$LOCK/pid" 2>/dev/null || true)"
  if [ -n "$holder" ] && kill -0 "$holder" 2>/dev/null; then
    trap - ERR
    echo "STOPPED: the tests are already running (pid $holder). Only one run at a time." >&2
    exit 75
  fi
  rm -rf "$LOCK"  # left by a run that died
  mkdir "$LOCK"
fi
echo $$ >"$LOCK/pid"
trap 'rm -rf "$LOCK"' EXIT

fingerprint() {
  {
    printf '%s\n' "$TEST_CMD"
    git ls-files -z --cached --others --exclude-standard -- "${WATCH[@]}" | sort -z \
      | while IFS= read -r -d '' file; do
          [ -f "$file" ] && printf '%s  %s\n' "$(git hash-object -- "$file")" "$file"
        done
  } | git hash-object --stdin
}

STEP="Fingerprinting"
before="$(fingerprint)"
if [ "$force" = "0" ] && [ "$before" = "$(cat "$STATE/passed" 2>/dev/null || true)" ]; then
  echo "==> Tests already passed for this code; not running them again (--force to run anyway)."
  exit 0
fi
run "Tests" "$TEST_CMD"
# Only if nothing changed while it ran.
[ "$(fingerprint)" != "$before" ] || echo "$before" >"$STATE/passed"
echo "==> Tests passed."  # no notification: the script that started it says how it ended
