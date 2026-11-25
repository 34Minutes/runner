#!/bin/bash
# Merge: fast-forward the main branch to the branch you're on. Never pushes.
#
# Move the main branch forward to the branch you're on (fast-forward
# only), then switch to main. It never pushes. It stops, changing nothing,
# on main already, with uncommitted changes, with nothing new to merge, or
# when main has moved on (rebase first).
# A Runner template (`runner template copy merge`). It's yours now: change
# the settings, or anything else, to suit this project.
#
#   scripts/merge.sh
set -euo pipefail

# ---------------------------------------------------------------- settings
PROJECT_DIR=".."     # the project's folder, from this script's folder
PROJECT_NAME=""      # for notifications and the log folder; empty: the folder's name
MAIN_BRANCH="main"
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

# ---------------------------------------------------------------- the merge
STEP="Checking the repository"
branch="$(git symbolic-ref --short -q HEAD || true)"
[ -n "$branch" ] || fail "You're not on a branch. Switch to the branch you want to merge first."
[ "$branch" != "$MAIN_BRANCH" ] || fail "You're on $MAIN_BRANCH, so there's nothing to merge. Switch to the branch you want to merge first."
git rev-parse -q --verify "refs/heads/$MAIN_BRANCH" >/dev/null || fail "There is no $MAIN_BRANCH branch. Check MAIN_BRANCH in $0."
if ! git diff --quiet || ! git diff --cached --quiet; then
  fail "There are uncommitted changes. Commit or stash them first."
fi
count="$(git rev-list --count "$MAIN_BRANCH..$branch")"
[ "$count" -gt 0 ] || fail "$branch has nothing that $MAIN_BRANCH doesn't."
git merge-base --is-ancestor "$MAIN_BRANCH" "$branch" \
  || fail "$MAIN_BRANCH has commits that $branch doesn't. Rebase $branch onto $MAIN_BRANCH first."

STEP="Merging"
git checkout --quiet "$MAIN_BRANCH"
git merge --quiet --ff-only "$branch"
succeed "Merged $branch into $MAIN_BRANCH ($count commit(s)). Not pushed."
