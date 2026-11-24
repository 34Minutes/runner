#!/bin/bash
set -euo pipefail

# Make a release: bump the version, date the changelog, commit, tag, push.
# Run it as: runner project release [--patch | --minor | --major] [--publish | --no-publish]
#
# Without --patch/--minor/--major it asks which. It checks first and stops,
# changing nothing, unless you're on the main branch with no uncommitted
# changes, level with the remote, and the changelog has Unreleased entries.
# Then it runs the lint and test commands, writes the version, commits
# "release: <version>" and tags it. Without --publish/--no-publish it asks
# before pushing; if you say no, the commit and tag stay here for push.

part=""
publish=""
for arg in "$@"; do
  case "$arg" in
    --patch|--minor|--major) part="${arg#--}" ;;
    --publish) publish="yes" ;;
    --no-publish) publish="no" ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

source "$(dirname "${BASH_SOURCE[0]}")/run.sh"
start_run release
remote="$RUNNER_REMOTE"
main="$RUNNER_MAIN_BRANCH"

STEP="Checking the repository"
branch="$(git symbolic-ref --short -q HEAD || true)"
[ "$branch" = "$main" ] || fail "Releases are made from $main, and you're on ${branch:-no branch}."
if ! git diff --quiet || ! git diff --cached --quiet; then
  fail "There are uncommitted changes. Commit them before releasing."
fi
git remote get-url "$remote" >/dev/null 2>&1 || fail "There is no remote called $remote. Add it, or fix project.remote."

STEP="Fetching from $remote"
git fetch --quiet "$remote"
if git rev-parse --verify -q "refs/remotes/$remote/$main" >/dev/null; then
  behind="$(git rev-list --count "HEAD..$remote/$main")"
  [ "$behind" -eq 0 ] || fail "$remote has $behind commit(s) on $main that you don't. Pull them first."
fi

STEP="Choosing the version"
current="$(runner_self project version 2>&1)" || fail "${current#runner project: }"
[ -n "$current" ] || fail "Couldn't read the project's version. Run runner project check."
if [ -z "$part" ]; then
  # Each choice shows the version it makes; a dry run also checks the changelog.
  options=()
  for level in patch minor major; do
    next="$(runner_self project bump "$level" --dry-run 2>&1)" || fail "${next#runner project: }"
    options+=("$(tr '[:lower:]' '[:upper:]' <<<"${level:0:1}")${level:1} ($current -> $next)")
  done
  picked="$(choose "Release which version?" "${options[@]}")"
  [ -n "$picked" ] || fail "Release cancelled. Nothing was changed."
  part="$(tr '[:upper:]' '[:lower:]' <<<"${picked%% *}")"
fi
version="$(runner_self project bump "$part" --dry-run 2>&1)" || fail "${version#runner project: }"
tag="$(runner_self project tag "$version")"
if git rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
  fail "There is already a $tag tag."
fi
echo "==> Releasing $version ($part, from $current), tag $tag"

[ -z "$RUNNER_LINT" ] || run_command "Lint" "$RUNNER_LINT"
[ -z "$RUNNER_TEST" ] || run_command "Tests" "$RUNNER_TEST"

STEP="Writing the version"
written="$(runner_self project bump "$part" --print-files 2>&1)" || fail "${written#runner project: }"
files=()
while IFS= read -r file; do
  if [ -n "$file" ]; then files+=("$file"); fi
done <<<"$written"
[ "${#files[@]}" -gt 0 ] || fail "Writing the version changed no files. Run runner project check."

STEP="Committing and tagging"
git add -- "${files[@]}"
git commit --quiet -m "release: $version"
git tag -a "$tag" -m "$version"

if [ -z "$publish" ]; then
  STEP="Asking before pushing"
  if [ "$RUNNER_PUBLISHES" = "1" ]; then
    question="$RUNNER_PROJECT_NAME $version is committed and tagged. Publish it now? Pushing the tag makes a public release."
    button="Publish"
  else
    question="$RUNNER_PROJECT_NAME $version is committed and tagged. Push it to $remote now?"
    button="Push"
  fi
  if confirm "$question" "$button"; then publish="yes"; else publish="no"; fi
fi
if [ "$publish" = "no" ]; then
  succeed "$version is committed and tagged here, not pushed. Run push when you're ready."
  exit 0
fi

STEP="Pushing to $remote"
git push --quiet "$remote" "$main" "refs/tags/$tag"
if [ "$RUNNER_PUBLISHES" = "1" ]; then
  succeed "$version is pushed and publishing."
else
  succeed "$version is pushed, with tag $tag."
fi
