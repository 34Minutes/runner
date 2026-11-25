#!/bin/bash
# Release: bump the version, date the changelog, commit, tag, then ask before pushing.
#
# Bump the version, date the changelog, commit, tag, and (after
# asking) push. It asks patch, minor or major, runs the lint check and tests,
# writes the new version into every VERSION_FILES file, moves the changelog's
# Unreleased entries under "## [x.y.z] - date", commits "release: x.y.z" and
# tags it. It stops, changing nothing, off the main branch, with uncommitted
# changes, behind the remote, with nothing under Unreleased, or if a lint or
# test fails.
# A Runner template (`runner template copy release`). It's yours now: change
# the settings, or anything else, to suit this project.
#
#   scripts/release.sh [--patch | --minor | --major] [--publish | --no-publish]
set -euo pipefail

# ---------------------------------------------------------------- settings
PROJECT_DIR=".."     # the project's folder, from this script's folder
PROJECT_NAME=""      # for notifications and the log folder; empty: the folder's name
MAIN_BRANCH="main"
REMOTE="origin"
# Where the version is written. The first is read; all are written. Each holds
# version = "1.2.3", "version": "1.2.3" or __version__ = "1.2.3", or is a
# VERSION file holding only 1.2.3.
VERSION_FILES=("pyproject.toml")
# A Keep a Changelog file: "## [Unreleased]" with "### Added", "### Fixed"...
CHANGELOG="CHANGELOG.md"
KEEP_UNRELEASED="Planned"   # subsections that stay under Unreleased (space-separated)
TAG_FORMAT="v%s"            # the tag, as a printf format for the version
LINT_CMD=""                 # for example: ruff check .   (empty: no lint step)
TEST_CMD=""                 # for example: pytest -q      (empty: no test step)
PUBLISHES=0                 # 1 if pushing the tag publishes something (a CI release, say)
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

# read_version FILE: the x.y.z it states, or nothing.
read_version() {
  perl -0ne 'if (/^\s*(?:__version__|"?version"?)\s*[:=]\s*"(\d+\.\d+\.\d+)"/m) { print $1 }
             elsif (/\A\s*(\d+\.\d+\.\d+)\s*\z/) { print $1 }' "$1"
}

# write_version FILE OLD NEW
write_version() {
  OLD="$2" NEW="$3" perl -0pi -e '
    s/^(\s*(?:__version__|"?version"?)\s*[:=]\s*")\Q$ENV{OLD}\E(")/$1$ENV{NEW}$2/m
      or s/\A(\s*)\Q$ENV{OLD}\E(\s*)\z/$1$ENV{NEW}$2/
      or die "no version $ENV{OLD} in $ARGV\n"' "$1"
}

# date_changelog FILE VERSION DATE: print the changelog with Unreleased
# entries moved under the new version. Fails, printing why, if it can't.
date_changelog() {
  VERSION="$2" DATE="$3" KEEP="$KEEP_UNRELEASED" perl -0e '
    my $text = do { local $/; open my $fh, "<", $ARGV[0] or die "There is no $ARGV[0].\n"; <$fh> };
    $text =~ /^## \[\Q$ENV{VERSION}\E\]/m and die "$ARGV[0] already has a $ENV{VERSION} section.\n";
    $text =~ /^## \[Unreleased\][^\n]*\n(.*?)(?=^## |\z)/ms
      or die "$ARGV[0] has no ## [Unreleased] section.\n";
    my ($body, $from, $to) = ($1, $-[1], $+[1]);
    my %keep = map { lc($_) => 1 } split " ", $ENV{KEEP};
    my (@kept, @moved);
    for my $part (split /^(?=### )/m, $body) {
      my ($head) = $part =~ /^### (.*)/ or next;
      (my $entries = $part) =~ s/^### .*\n?//;
      $part =~ s/\s+\z//;
      if ($keep{lc $head}) { push @kept, $part }
      elsif ($entries =~ /\S/) { push @moved, $part }
    }
    @moved or die "$ARGV[0] has no entries under Unreleased to release.\n";
    my $new = "\n" . join("", map { "$_\n\n" } @kept)
            . "## [$ENV{VERSION}] - $ENV{DATE}\n\n" . join("\n\n", @moved) . "\n\n";
    substr($text, $from, $to - $from) = $new;
    print $text;' "$1"
}

part=""
publish=""
for arg in "$@"; do
  case "$arg" in
    --patch|--minor|--major) part="${arg#--}" ;;
    --publish) publish="yes" ;;
    --no-publish) publish="no" ;;
    *) fail "Unknown option: $arg" ;;
  esac
done

# ---------------------------------------------------------------- the release
STEP="Checking the repository"
branch="$(git symbolic-ref --short -q HEAD || true)"
[ "$branch" = "$MAIN_BRANCH" ] || fail "Releases are made from $MAIN_BRANCH, and you're on ${branch:-no branch}."
if ! git diff --quiet || ! git diff --cached --quiet; then
  fail "There are uncommitted changes. Commit them before releasing."
fi
git remote get-url "$REMOTE" >/dev/null 2>&1 || fail "There is no remote called $REMOTE. Check REMOTE in $0."

STEP="Fetching from $REMOTE"
git fetch --quiet "$REMOTE"
if git rev-parse -q --verify "refs/remotes/$REMOTE/$MAIN_BRANCH" >/dev/null; then
  behind="$(git rev-list --count "HEAD..$REMOTE/$MAIN_BRANCH")"
  [ "$behind" -eq 0 ] || fail "$REMOTE has $behind commit(s) on $MAIN_BRANCH that you don't. Pull them first."
fi

STEP="Reading the version"
current=""
for file in "${VERSION_FILES[@]}"; do
  [ -f "$file" ] || fail "There is no $file. Check VERSION_FILES in $0."
  found="$(read_version "$file")"
  [ -n "$found" ] || fail "$file doesn't state a version like 1.2.3."
  [ -z "$current" ] || [ "$found" = "$current" ] || fail "$file says $found, but ${VERSION_FILES[0]} says $current."
  current="$found"
done
IFS=. read -r major minor patch <<<"$current"
next_for() {
  case "$1" in
    patch) echo "$major.$minor.$((patch + 1))" ;;
    minor) echo "$major.$((minor + 1)).0" ;;
    major) echo "$((major + 1)).0.0" ;;
  esac
}

if [ -z "$part" ]; then
  picked="$(choose "Release which version?" "Patch ($current -> $(next_for patch))" \
    "Minor ($current -> $(next_for minor))" "Major ($current -> $(next_for major))")"
  [ -n "$picked" ] || fail "Release cancelled. Nothing was changed."
  part="$(tr '[:upper:]' '[:lower:]' <<<"${picked%% *}")"
fi
version="$(next_for "$part")"
# shellcheck disable=SC2059
tag="$(printf "$TAG_FORMAT" "$version")"
! git rev-parse -q --verify "refs/tags/$tag" >/dev/null || fail "There is already a $tag tag."

STEP="Checking the changelog"
dated="$(mktemp)"
why="$(date_changelog "$CHANGELOG" "$version" "$(date +%Y-%m-%d)" 2>&1 >"$dated")" \
  || { rm -f "$dated"; fail "$why"; }
echo "==> Releasing $version ($part, from $current), tag $tag"

[ -z "$LINT_CMD" ] || run "Lint" "$LINT_CMD"
[ -z "$TEST_CMD" ] || run "Tests" "$TEST_CMD"

STEP="Writing the version"
for file in "${VERSION_FILES[@]}"; do write_version "$file" "$current" "$version"; done
cat "$dated" >"$CHANGELOG"
rm -f "$dated"

STEP="Committing and tagging"
git add -- "${VERSION_FILES[@]}" "$CHANGELOG"
git commit --quiet -m "release: $version"
git tag -a "$tag" -m "$version"

if [ -z "$publish" ]; then
  STEP="Asking before pushing"
  if [ "$PUBLISHES" = "1" ]; then
    question="$PROJECT_NAME $version is committed and tagged. Publish it now? Pushing the tag makes a public release."
    button="Publish"
  else
    question="$PROJECT_NAME $version is committed and tagged. Push it to $REMOTE now?"
    button="Push"
  fi
  if confirm "$question" "$button"; then publish="yes"; else publish="no"; fi
fi
if [ "$publish" = "no" ]; then
  succeed "$version is committed and tagged here, not pushed. Push it when you're ready."
  exit 0
fi

STEP="Pushing to $REMOTE"
git push --quiet "$REMOTE" "$MAIN_BRANCH" "refs/tags/$tag"
succeed "$version is pushed, with tag $tag."
