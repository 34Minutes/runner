#!/bin/bash
set -euo pipefail

# Fast-forward the main branch to the branch you're on, then switch to it.
# Run it as: runner project merge
#
# Only a fast-forward: main must not have moved on since the branch began.
# Anything else stops with the reason and changes nothing: you're on main
# already, uncommitted changes, nothing new on the branch, or main has
# commits the branch lacks (rebase it first). Nothing is pushed.

source "$(dirname "${BASH_SOURCE[0]}")/run.sh"
start_run merge
target="$RUNNER_MAIN_BRANCH"

STEP="Checking the branches"
branch="$(git symbolic-ref --short -q HEAD)" || fail "Not on a branch. Switch to the branch you want to merge."
if [ "$branch" = "$target" ]; then
  fail "You're on $target, so there's nothing to merge. Switch to the branch you want to merge first."
fi
git rev-parse --verify -q "refs/heads/$target" >/dev/null || fail "There is no $target branch here."
if ! git diff --quiet || ! git diff --cached --quiet; then
  fail "$branch has uncommitted changes. Commit them first."
fi
ahead="$(git rev-list --count "$target..$branch")"
[ "$ahead" -gt 0 ] || fail "$branch has nothing that $target doesn't already have."
if ! git merge-base --is-ancestor "$target" "$branch"; then
  extra="$(git rev-list --count "$branch..$target")"
  fail "$target has $extra commit(s) that $branch doesn't. Rebase $branch onto $target first."
fi

STEP="Merging"
git checkout --quiet "$target"
git merge --ff-only --quiet "$branch"

succeed "Merged $branch into $target ($ahead commit(s)). You're on $target now; nothing was pushed."
