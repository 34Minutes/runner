#!/bin/bash
# Latest: move the LATEST_RELEASE tag to a version you pick, and push it.
#
# Lists the version tags (newest first) with the one LATEST_RELEASE is on,
# asks which to point it at, asks once more before pushing, then moves the
# tag and force-pushes just that tag. It notes a version with no GitHub
# release (2.0.0 has none). Moving the tag builds and publishes nothing:
# only version tags start .github/workflows/release.yml.
#
#   scripts/latest.sh [VERSION] [--yes]
#
# VERSION skips the list. --yes skips the question before pushing.
set -euo pipefail

# ---------------------------------------------------------------- settings
PROJECT_DIR=".."       # the project's folder, from this script's folder
PROJECT_NAME="Runner"  # for notifications and the log folder
REMOTE="origin"
LATEST_TAG="LATEST_RELEASE"
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

# choose PROMPT ITEM...: prints the item picked, or nothing for Cancel.
choose() {
  _quiet && return 0
  command -v osascript >/dev/null 2>&1 || return 0
  local prompt="$1" items="" item answer
  shift
  for item in "$@"; do items="$items${items:+, }\"$(_as "$item")\""; done
  answer="$(osascript -e "choose from list {$items} with prompt \"$(_as "$prompt")\" \
with title \"$(_as "$TITLE")\" default items {\"$(_as "$1")\"}" 2>/dev/null || true)"
  [ "$answer" = "false" ] || printf '%s' "$answer"
}

# ---------------------------------------------------------------- the move
wanted=""
yes=0
for arg in "$@"; do
  case "$arg" in
    --yes) yes=1 ;;
    -h|--help) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) fail "Unknown option: $arg (try --help)" ;;
    *) wanted="$arg" ;;
  esac
done

STEP="Fetching tags from $REMOTE"
# --force takes the remote's LATEST_RELEASE even if it moved since this copy fetched it.
git fetch --quiet --force --tags "$REMOTE"

STEP="Reading the versions"
versions=()
while IFS= read -r tag; do
  [[ "$tag" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] && versions+=("$tag")
done < <(git tag -l --sort=-v:refname)
[ "${#versions[@]}" -gt 0 ] || fail "There are no version tags like 1.2.3 yet."

# Which version LATEST_RELEASE is on now: the version tag on the same commit.
current=""
if latest_commit="$(git rev-parse -q --verify "refs/tags/$LATEST_TAG^{commit}")"; then
  for v in "${versions[@]}"; do
    if [ "$(git rev-parse "refs/tags/$v^{commit}")" = "$latest_commit" ]; then current="$v"; break; fi
  done
  current="${current:-a commit with no version tag}"
fi

if [ -z "$wanted" ]; then
  items=()
  for v in "${versions[@]}"; do
    [ "$v" = "$current" ] && items+=("$v (now $LATEST_TAG)") || items+=("$v")
  done
  picked="$(choose "Point $LATEST_TAG at which version?" "${items[@]}")"
  [ -n "$picked" ] || fail "Cancelled. $LATEST_TAG was not moved."
  wanted="${picked%% *}"
fi
printf '%s\n' "${versions[@]}" | grep -qxF "$wanted" || fail "There is no version tag $wanted."
if [ "$wanted" = "$current" ]; then
  succeed "$LATEST_TAG is already on $wanted."
  exit 0
fi

note=""
if command -v gh >/dev/null 2>&1 && ! gh release view "$wanted" >/dev/null 2>&1; then
  note=" $wanted has no GitHub release, so there is nothing to download for it."
  echo "==> Note:$note"
fi

STEP="Asking before pushing"
if [ "$yes" -eq 0 ]; then
  from="${current:-nowhere yet}"
  confirm "Move $LATEST_TAG from $from to $wanted and push it to $REMOTE?$note Anyone who already fetched the tag keeps the old one until they fetch tags with --force." "Move" \
    || fail "Cancelled. $LATEST_TAG was not moved."
fi

STEP="Moving $LATEST_TAG"
git tag -fa "$LATEST_TAG" -m "Latest release: $wanted" "refs/tags/$wanted^{commit}"
STEP="Pushing $LATEST_TAG to $REMOTE"
git push --quiet --force "$REMOTE" "refs/tags/$LATEST_TAG"
succeed "$LATEST_TAG is on $wanted (was ${current:-not set})."
