#!/bin/bash
# Deploy: install the Mac build into /Applications and restart Runner.
#
# Rebuilds first (lint, tests, build) only when dist/Runner.app is missing,
# is a different version, or is older than the code. Otherwise it installs
# the build that is there. Runner quits and starts again on the way, so this
# keeps running after the Runner that started it has gone.
#
#   scripts/deploy.sh            build if out of date, then install
#   scripts/deploy.sh --rebuild  always build first
set -euo pipefail

# ---------------------------------------------------------------- settings
PROJECT_DIR=".."       # the project's folder, from this script's folder
PROJECT_NAME="Runner"  # for notifications and the log folder
BUILD_CMD="./scripts/build-mac.sh"      # lints and tests first (scripts/run_tests.py)
INSTALL_CMD="./scripts/install-mac.sh"  # quits Runner, swaps the app, starts it
APP="dist/Runner.app"
# A build is out of date when any of these changed after it was made.
SOURCES=(src runner.spec pyproject.toml assets)
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

# ---------------------------------------------------------------- the deploy
REBUILD=0
for arg in "$@"; do
  case "$arg" in
    --rebuild) REBUILD=1 ;;
    -h|--help) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) fail "Unknown option: $arg (try --help)" ;;
  esac
done

[ "$(uname)" = "Darwin" ] || fail "Deploy installs the Mac app, so it runs on macOS only."

# Why the build in dist/ can't be installed as it is. Empty when it can.
stale_reason() {
  local plist="$APP/Contents/Info.plist" built wanted newer
  [ -f "$plist" ] || { echo "there is no build yet"; return; }
  built="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$plist" 2>/dev/null || true)"
  wanted="$(.venv/bin/python scripts/check_version.py 2>/dev/null || true)"
  if [ -n "$wanted" ] && [ "$built" != "$wanted" ]; then
    echo "the build is $built and the code is $wanted"
    return
  fi
  newer="$(find "${SOURCES[@]}" -type f -newer "$plist" \
    -not -path '*/__pycache__/*' -not -name '.DS_Store' -print -quit 2>/dev/null || true)"
  [ -z "$newer" ] || echo "${newer} changed after the last build"
}

if [ "$REBUILD" -eq 1 ]; then
  REASON="--rebuild was given"
else
  REASON="$(stale_reason)"
fi
if [ -n "$REASON" ]; then
  echo "==> Building first: $REASON."
  run "Build" "$BUILD_CMD"
else
  echo "==> $APP is up to date with the code; installing it as it is."
fi
run "Install" "$INSTALL_CMD"
succeed "Deployed $(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$APP/Contents/Info.plist")."
