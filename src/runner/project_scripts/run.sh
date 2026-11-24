# shellcheck shell=bash
# Shared by Runner's project scripts: a log of each run, and a notification
# saying how it ended. Started by `runner project <script>`, which reads the
# project's .runner/project.toml and passes it on in these variables:
#
#   RUNNER_PROJECT_ROOT  RUNNER_PROJECT_NAME  RUNNER_MAIN_BRANCH  RUNNER_REMOTE
#   RUNNER_TAG_PATTERN   RUNNER_LINT  RUNNER_TEST  RUNNER_BUILD   RUNNER_PUBLISHES
#   RUNNER_SELF (+ RUNNER_SELF_MODULE): how to call `runner` back
#   RUNNER_SCRIPTS_LOG_DIR: where the logs go
#
# A script may be started from a Runner launcher, with no terminal, so each
# run's output goes to $RUNNER_SCRIPTS_LOG_DIR/<script>.log (the last run
# only) as well as to the terminal, when there is one.
#
# RUNNER_SCRIPTS_QUIET=1 skips notifications and dialogs (for tests); a dialog
# then answers as if Cancel were pressed unless the script was given its
# answer as an option.

: "${RUNNER_PROJECT_ROOT:?Start this with: runner project <script>}"
STEP="Starting"
RUN_TITLE="Runner"
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
  if command -v osascript >/dev/null 2>&1; then
    osascript -e "display notification \"$(_as_text "$message")\" with title \"$(_as_text "$title")\"" \
      >/dev/null 2>&1 || true
  elif command -v notify-send >/dev/null 2>&1; then
    notify-send "$title" "$message" >/dev/null 2>&1 || true
  fi
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

# start_run SCRIPT: begin logging and catch any command that fails.
start_run() {
  RUN_TITLE="$RUNNER_PROJECT_NAME $1"
  mkdir -p "$LOG_DIR"
  LOG="$LOG_DIR/$1.log"
  : >"$LOG"
  exec > >(tee -a "$LOG") 2>&1
  echo "==> $RUN_TITLE, $(date '+%Y-%m-%d %H:%M:%S'), in $RUNNER_PROJECT_ROOT"
  set -o errtrace  # a failure inside a function is caught too
  trap _on_failure ERR
  cd "$RUNNER_PROJECT_ROOT"
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

# run_command NAME COMMAND: a command from the project file, in the project folder.
run_command() {
  STEP="$1"
  echo "==> $1: $2"
  bash -c "$2"
}

# runner_self ARGS...: call `runner` back, for the parts written in Python.
runner_self() {
  if [ -n "${RUNNER_SELF_MODULE:-}" ]; then
    "$RUNNER_SELF" -m runner "$@"
  else
    "$RUNNER_SELF" "$@"
  fi
}

# confirm MESSAGE BUTTON: true if the user presses BUTTON (not Cancel).
confirm() {
  [ "${RUNNER_SCRIPTS_QUIET:-0}" = "1" ] && return 1
  command -v osascript >/dev/null 2>&1 || return 1
  osascript -e "display dialog \"$(_as_text "$1")\" buttons {\"Cancel\", \"$(_as_text "$2")\"} \
default button \"Cancel\" cancel button \"Cancel\" with title \"$(_as_text "$RUN_TITLE")\"" >/dev/null 2>&1
}

# choose PROMPT ITEM...: prints the item picked, or nothing for Cancel.
choose() {
  [ "${RUNNER_SCRIPTS_QUIET:-0}" = "1" ] && return 0
  command -v osascript >/dev/null 2>&1 || return 0
  local prompt="$1" items="" item answer
  shift
  for item in "$@"; do
    items="$items${items:+, }\"$(_as_text "$item")\""
  done
  answer="$(osascript -e "choose from list {$items} with prompt \"$(_as_text "$prompt")\" \
with title \"$(_as_text "$RUN_TITLE")\" default items {\"$(_as_text "$1")\"}" 2>/dev/null || true)"
  [ "$answer" = "false" ] || printf '%s' "$answer"
}
