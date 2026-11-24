# shellcheck shell=bash
# Shared by the scripts in scripts/: a log of each run, and a macOS
# notification saying how it ended. Source it, then call start_run.
#
#   source "$(dirname "${BASH_SOURCE[0]}")/lib/run.sh"
#   start_run "Runner push" push
#   STEP="Checking the branch"   # named in the failure notification
#   fail "Nothing to push."      # a deliberate stop, with the reason
#   succeed "Pushed 2 commits."  # the success notification
#
# Every script here may be started from a Runner launcher, with no terminal,
# so each run's output goes to ~/Library/Logs/Runner Scripts/<name>.log (the
# last run only) as well as to the terminal, when there is one.
#
# Set RUNNER_SCRIPTS_QUIET=1 to skip notifications and dialogs (for tests);
# a dialog then answers as if Cancel were pressed unless the script was given
# its answer as an option.

STEP="Starting"
RUN_TITLE="Runner script"
LOG_DIR="${RUNNER_SCRIPTS_LOG_DIR:-$HOME/Library/Logs/Runner Scripts}"
LOG=""

# AppleScript strings end at a double quote, so they become single quotes.
_as_text() {
  local text="$1"
  printf '%s' "${text//\"/\'}"
}

notify() {
  local title="$1" message="$2"
  [ "${RUNNER_SCRIPTS_QUIET:-0}" = "1" ] && return 0
  osascript -e "display notification \"$(_as_text "$message")\" with title \"$(_as_text "$title")\"" \
    >/dev/null 2>&1 || true
}

_log_hint() {
  printf '%s' "Log: ${LOG/#$HOME/~}"
}

_on_failure() {
  local code=$?
  # errtrace runs this in $(...) subshells too. The script itself reports a
  # failure there when it sees the result, or passes it to fail on purpose.
  [ "$BASH_SUBSHELL" -eq 0 ] || return 0
  echo "ERROR: $STEP failed (exit $code)" >&2
  notify "$RUN_TITLE failed" "$STEP failed (exit $code). $(_log_hint)"
}

# start_run TITLE NAME: begin logging and catch any command that fails.
start_run() {
  RUN_TITLE="$1"
  mkdir -p "$LOG_DIR"
  LOG="$LOG_DIR/$2.log"
  : >"$LOG"
  exec > >(tee -a "$LOG") 2>&1
  echo "==> $RUN_TITLE, $(date '+%Y-%m-%d %H:%M:%S')"
  set -o errtrace  # a failure inside a function is caught too
  trap _on_failure ERR
}

# fail MESSAGE: stop here on purpose, saying why.
fail() {
  trap - ERR
  echo "STOPPED: $1" >&2
  notify "$RUN_TITLE stopped" "$1"
  exit 1
}

# succeed MESSAGE: the run worked.
succeed() {
  echo "==> $1"
  notify "$RUN_TITLE" "$1"
}

# confirm MESSAGE BUTTON: true if the user presses BUTTON (not Cancel).
confirm() {
  [ "${RUNNER_SCRIPTS_QUIET:-0}" = "1" ] && return 1
  osascript -e "display dialog \"$(_as_text "$1")\" buttons {\"Cancel\", \"$(_as_text "$2")\"} \
default button \"Cancel\" cancel button \"Cancel\" with title \"$(_as_text "$RUN_TITLE")\"" >/dev/null 2>&1
}

# choose PROMPT ITEM...: prints the item picked, or nothing for Cancel.
choose() {
  [ "${RUNNER_SCRIPTS_QUIET:-0}" = "1" ] && return 0
  local prompt="$1" items="" item answer
  shift
  for item in "$@"; do
    items="$items${items:+, }\"$(_as_text "$item")\""
  done
  answer="$(osascript -e "choose from list {$items} with prompt \"$(_as_text "$prompt")\" \
with title \"$(_as_text "$RUN_TITLE")\" default items {\"$(_as_text "$1")\"}" 2>/dev/null || true)"
  [ "$answer" = "false" ] || printf '%s' "$answer"
}

# The repository these scripts belong to, whatever folder they start in.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
