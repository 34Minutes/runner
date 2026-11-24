#!/bin/bash
set -euo pipefail

# Push the current branch to GitHub, with any new release tags on it.
#
# Usage: ./scripts/push.sh
#
# It checks first and stops, saying why, when GitHub has commits you don't
# (pull first) or you're not on a branch. A new release tag (like 1.1.3)
# starts the release workflow, which publishes a public GitHub release, so
# it asks before pushing one. A notification says how it ended; the run is
# logged to ~/Library/Logs/Runner Scripts/push.log.

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  sed -n '4,11p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
fi

source "$(dirname "${BASH_SOURCE[0]}")/lib/run.sh"
start_run "Runner push" push
cd "$REPO_ROOT"

STEP="Checking the branch"
branch="$(git symbolic-ref --short -q HEAD)" || fail "Not on a branch, so there is nothing to push."

STEP="Fetching from GitHub"
git fetch --quiet origin

STEP="Comparing with GitHub"
if git rev-parse --verify -q "refs/remotes/origin/$branch" >/dev/null; then
  behind="$(git rev-list --count "HEAD..origin/$branch")"
  if [ "$behind" -gt 0 ]; then
    fail "GitHub has $behind commit(s) on $branch that you don't. Pull them first."
  fi
  ahead="$(git rev-list --count "origin/$branch..HEAD")"
else
  ahead="$(git rev-list --count HEAD)"  # a branch GitHub doesn't have yet
fi

# Release tags on this branch that GitHub doesn't have.
remote_tags="$(git ls-remote --tags --refs origin | sed 's#.*refs/tags/##')"
new_tags=()
while IFS= read -r tag; do
  [ -n "$tag" ] || continue
  if ! grep -qxF "$tag" <<<"$remote_tags"; then
    new_tags+=("$tag")
  fi
done < <(git tag --merged HEAD | grep -E '^[0-9]+\.[0-9]+\.[0-9]+$' || true)

if [ "$ahead" -eq 0 ] && [ "${#new_tags[@]}" -eq 0 ]; then
  succeed "Nothing to push: $branch is already up to date on GitHub."
  exit 0
fi

published=""
if [ "${#new_tags[@]}" -gt 0 ]; then
  published="${new_tags[*]}"
  STEP="Asking before publishing"
  confirm "Pushing will also publish release $published on GitHub, where anyone can see it." \
    "Push and publish" || fail "Didn't push: publishing release $published was cancelled."
fi

STEP="Pushing to GitHub"
refs=("$branch")
for tag in ${new_tags[@]+"${new_tags[@]}"}; do
  refs+=("refs/tags/$tag")
done
git push origin "${refs[@]}"

message="Pushed $ahead commit(s) on $branch to GitHub."
[ -n "$published" ] && message="$message Release $published is publishing."
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  message="$message Uncommitted changes were left out."
fi
succeed "$message"
