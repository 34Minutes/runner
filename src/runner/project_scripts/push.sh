#!/bin/bash
set -euo pipefail

# Push the current branch, with any new release tags on it.
# Run it as: runner project push
#
# It checks first and stops, saying why, when the remote has commits you
# don't (pull first) or you're not on a branch. If the project publishes on
# a release tag, it asks before pushing a new one.

source "$(dirname "${BASH_SOURCE[0]}")/run.sh"
start_run push
remote="$RUNNER_REMOTE"

STEP="Checking the branch"
branch="$(git symbolic-ref --short -q HEAD)" || fail "Not on a branch, so there is nothing to push."
git remote get-url "$remote" >/dev/null 2>&1 || fail "There is no remote called $remote. Add it, or fix project.remote."

STEP="Fetching from $remote"
git fetch --quiet "$remote"

STEP="Comparing with $remote"
if git rev-parse --verify -q "refs/remotes/$remote/$branch" >/dev/null; then
  behind="$(git rev-list --count "HEAD..$remote/$branch")"
  if [ "$behind" -gt 0 ]; then
    fail "$remote has $behind commit(s) on $branch that you don't. Pull them first."
  fi
  ahead="$(git rev-list --count "$remote/$branch..HEAD")"
else
  ahead="$(git rev-list --count HEAD)"  # a branch the remote doesn't have yet
fi

# Release tags on this branch that the remote doesn't have.
remote_tags="$(git ls-remote --tags --refs "$remote" | sed 's#.*refs/tags/##')"
new_tags=()
while IFS= read -r tag; do
  [ -n "$tag" ] || continue
  if ! grep -qxF "$tag" <<<"$remote_tags"; then
    new_tags+=("$tag")
  fi
done < <(git tag --merged HEAD | grep -E "$RUNNER_TAG_PATTERN" || true)

if [ "$ahead" -eq 0 ] && [ "${#new_tags[@]}" -eq 0 ]; then
  succeed "Nothing to push: $branch is already up to date on $remote."
  exit 0
fi

tags_text=""
if [ "${#new_tags[@]}" -gt 0 ]; then
  tags_text="${new_tags[*]}"
  if [ "$RUNNER_PUBLISHES" = "1" ]; then
    STEP="Asking before publishing"
    confirm "Pushing will also publish release $tags_text, where anyone can see it." \
      "Push and publish" || fail "Didn't push: publishing release $tags_text was cancelled."
  fi
fi

STEP="Pushing to $remote"
refs=("$branch")
for tag in ${new_tags[@]+"${new_tags[@]}"}; do
  refs+=("refs/tags/$tag")
done
git push "$remote" "${refs[@]}"

message="Pushed $ahead commit(s) on $branch to $remote."
if [ -n "$tags_text" ]; then
  if [ "$RUNNER_PUBLISHES" = "1" ]; then
    message="$message Release $tags_text is publishing."
  else
    message="$message Tag $tags_text too."
  fi
fi
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  message="$message Uncommitted changes were left out."
fi
succeed "$message"
