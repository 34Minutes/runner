#!/bin/bash
set -euo pipefail

# Make a release: bump the version, date the changelog, commit, tag, publish.
#
# Usage: ./scripts/release.sh [--patch | --minor | --major] [--publish | --no-publish]
#
# Without --patch/--minor/--major it asks which. It checks first and stops,
# changing nothing, unless you're on main with no uncommitted changes, level
# with GitHub, and CHANGELOG.md has Unreleased entries. Then it runs the lint
# check and tests, writes the version (scripts/bump_version.py), commits
# "release: <version>" and tags it. Pushing the tag publishes a public GitHub
# release, so without --publish/--no-publish it asks first; if you say no,
# the commit and tag stay here for the Push launcher. A notification says
# how it ended; the run is logged to ~/Library/Logs/Runner Scripts/release.log.

part=""
publish=""
for arg in "$@"; do
  case "$arg" in
    --patch|--minor|--major) part="${arg#--}" ;;
    --publish) publish="yes" ;;
    --no-publish) publish="no" ;;
    -h|--help) sed -n '4,15p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

source "$(dirname "${BASH_SOURCE[0]}")/lib/run.sh"
start_run "Runner release" release
cd "$REPO_ROOT"
PY="$REPO_ROOT/.venv/bin/python"
# A Qt path left in the shell makes the venv load a second Qt (see build-mac.sh).
unset QT_PLUGIN_PATH QT_QPA_PLATFORM_PLUGIN_PATH

STEP="Checking the repository"
[ -x "$PY" ] || fail "The project's .venv is missing."
branch="$(git symbolic-ref --short -q HEAD || true)"
[ "$branch" = "main" ] || fail "Releases are made from main, and you're on ${branch:-no branch}."
if ! git diff --quiet || ! git diff --cached --quiet; then
  fail "There are uncommitted changes. Commit them before releasing."
fi

STEP="Fetching from GitHub"
git fetch --quiet origin
behind="$(git rev-list --count HEAD..origin/main)"
[ "$behind" -eq 0 ] || fail "GitHub has $behind commit(s) on main that you don't. Pull them first."

STEP="Choosing the version"
current="$("$PY" scripts/check_version.py)"
if [ -z "$part" ]; then
  # Each choice shows the version it makes; a dry run also checks the changelog.
  options=()
  for level in patch minor major; do
    next="$("$PY" scripts/bump_version.py "$level" --dry-run 2>&1)" || fail "${next#ERROR: }"
    options+=("$(tr '[:lower:]' '[:upper:]' <<<"${level:0:1}")${level:1} ($current -> $next)")
  done
  picked="$(choose "Release which version?" "${options[@]}")"
  [ -n "$picked" ] || fail "Release cancelled. Nothing was changed."
  part="$(tr '[:upper:]' '[:lower:]' <<<"${picked%% *}")"
fi
version="$("$PY" scripts/bump_version.py "$part" --dry-run 2>&1)" || fail "${version#ERROR: }"
if git rev-parse -q --verify "refs/tags/$version" >/dev/null; then
  fail "There is already a $version tag."
fi
echo "==> Releasing $version ($part, from $current)"

STEP="Lint check"
"$PY" -m ruff check src tests
STEP="Tests"
"$PY" -m pytest -q --capture=sys

STEP="Writing the version"
"$PY" scripts/bump_version.py "$part" >/dev/null
"$PY" scripts/check_version.py --tag "$version" >/dev/null

STEP="Committing and tagging"
git add pyproject.toml src/runner/__init__.py CHANGELOG.md
git commit --quiet -m "release: $version"
git tag -a "$version" -m "$version"

if [ -z "$publish" ]; then
  STEP="Asking before publishing"
  if confirm "Runner $version is committed and tagged. Publish it now? GitHub builds it and makes a public release." \
    "Publish"; then
    publish="yes"
  else
    publish="no"
  fi
fi
if [ "$publish" = "no" ]; then
  succeed "Runner $version is committed and tagged here, not published. Push with the Push launcher to publish."
  exit 0
fi

STEP="Pushing to GitHub"
git push --quiet origin main "refs/tags/$version"
succeed "Runner $version is pushed. GitHub is building and publishing the release."
