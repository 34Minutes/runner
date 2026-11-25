#!/bin/bash
# Push: push the branch you're on and its new release tags. Asks before publishing.
#
# Push the branch you're on, and any release tags on it that the remote
# doesn't have. It stops, changing nothing, when the remote has commits you
# don't (pull first). If pushing a tag publishes something, it asks first.
# A Runner template (`runner template copy push`). It's yours now: change
# the settings, or anything else, to suit this project.
#
#   scripts/push.sh
set -euo pipefail

# ---------------------------------------------------------------- settings
PROJECT_DIR=".."     # the project's folder, from this script's folder
PROJECT_NAME="Runner"  # for notifications and the log folder
REMOTE="origin"
TAG_GLOB="[0-9]*"  # release tags are 1.2.3, no "v"
PUBLISHES=1  # pushing a tag starts .github/workflows/release.yml
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

# confirm MESSAGE BUTTON: true if the user presses BUTTON, not Cancel.
confirm() {
  _quiet && return 1
  command -v osascript >/dev/null 2>&1 || return 1
  osascript -e "display dialog \"$(_as "$1")\" buttons {\"Cancel\", \"$(_as "$2")\"} \
default button \"Cancel\" cancel button \"Cancel\" with title \"$(_as "$TITLE")\"" >/dev/null 2>&1
}

# ---------------------------------------------------------------- the push
STEP="Checking the repository"
branch="$(git symbolic-ref --short -q HEAD || true)"
[ -n "$branch" ] || fail "You're not on a branch."
git remote get-url "$REMOTE" >/dev/null 2>&1 || fail "There is no remote called $REMOTE. Check REMOTE in $0."

STEP="Fetching from $REMOTE"
git fetch --quiet "$REMOTE"
if git rev-parse -q --verify "refs/remotes/$REMOTE/$branch" >/dev/null; then
  behind="$(git rev-list --count "HEAD..$REMOTE/$branch")"
  [ "$behind" -eq 0 ] || fail "$REMOTE has $behind commit(s) on $branch that you don't. Pull them first."
fi
# Commits on this branch that aren't on $REMOTE in any branch.
ahead="$(git rev-list --count HEAD --not --remotes="$REMOTE")"

STEP="Finding new tags"
remote_tags="$(git ls-remote --tags --refs "$REMOTE" | sed 's#.*refs/tags/##')"
new_tags=()
while IFS= read -r tag; do
  [ -n "$tag" ] || continue
  grep -qxF "$tag" <<<"$remote_tags" || new_tags+=("$tag")
done < <(git tag --merged HEAD --list "$TAG_GLOB")

if [ "$ahead" -eq 0 ] && [ "${#new_tags[@]}" -eq 0 ]; then
  succeed "Nothing to push: $branch is already up to date on $REMOTE."
  exit 0
fi
if [ "${#new_tags[@]}" -gt 0 ] && [ "$PUBLISHES" = "1" ]; then
  STEP="Asking before publishing"
  confirm "Pushing ${new_tags[*]} publishes a release. Push it now?" "Publish" \
    || fail "Not pushed: publishing release ${new_tags[*]} was cancelled."
fi

STEP="Pushing to $REMOTE"
refs=("$branch")
for tag in "${new_tags[@]+"${new_tags[@]}"}"; do refs+=("refs/tags/$tag"); done
git push --quiet "$REMOTE" "${refs[@]}"
message="Pushed $ahead commit(s) on $branch to $REMOTE."
[ "${#new_tags[@]}" -eq 0 ] || message="$message Tags: ${new_tags[*]}."
succeed "$message"
