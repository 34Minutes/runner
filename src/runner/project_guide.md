# runner project: setting a project up for Runner (a guide for LLMs and people)

Runner is the user's desktop launcher. `runner project` gives a code project
four launchers in Runner, **Build**, **Merge**, **Push** and **Release**, run by
scripts that ship inside Runner. The scripts read one file in the project,
`.runner/project.toml`. Your job, when the user asks you to set a project up
for Runner, is to make that file right and the project ready, then create the
launchers. The user clicks them; you can't run them from Runner.

Print this guide any time with `runner project guide`. For launchers in
general (not tied to a project), see `runner ctl guide`.

## Find the command

Use the first that works: `runner project --help`, then
`/Applications/Runner.app/Contents/MacOS/Runner project --help`. Run every
command below from inside the project's folder, or add `--project PATH`.

## Set up a project: the steps

1. **`runner project init`** writes `.runner/project.toml`, filled in with what
   it detects: name, main branch, remote, version file(s), changelog, and
   lint, test and build commands. It won't overwrite an existing file
   (`--force` does).
2. **Read the file and fix every value.** Detection is a guess. Check each
   line against the project, fill in what's empty, and remove guesses that are
   wrong. The fields are explained below and in the file's comments.
3. **Make the project match** what the file says (next section). This is
   usually: add a changelog, make sure the version is in one place, make sure
   the test command passes.
4. **`runner project check`** reports each part as `ok`, `note` or `FIX`.
   Fix every `FIX` and run it again until it ends with `Ready.` A `note` is
   fine: it tells you something is off or unused by choice.
5. **`runner project launchers --as <your name>`** (for example `--as claude`)
   creates or updates a launcher per script and a container group named
   "<name> Scripts" holding them. It's safe to run again; it updates instead
   of duplicating.
6. **Commit `.runner/project.toml`** (and any changelog you created) so the
   setup travels with the project.
7. **Tell the user** what you set up: the container group's name, which
   launchers it has, and anything they must do (for example: "Release is
   missing because the project has no version").

## What the project must have

| Needed for | What | Notes |
| --- | --- | --- |
| All | A **git repository** | `git init` if there isn't one. |
| Merge, Release | A **main branch** (`project.main_branch`) | Usually `main` or `master`. |
| Push, Release | A **remote** (`project.remote`) | Usually `origin`. |
| Release | A **version** stated in one file (`version.file`) | See formats below. Other files that repeat it go in `version.also`; Release keeps them all equal and refuses if they already differ. |
| Release | A **changelog** in Keep a Changelog format (`changelog.file`) | See below. |
| Release | **Lint** and **test** commands (optional) | Run before anything changes; a failure stops the release. |
| Build | A **build** command (`commands.build`) | Without one there's no Build launcher. |

**Version formats** `version.file` can hold, using the first match:

- `version = "1.2.3"` (pyproject.toml, Cargo.toml)
- `"version": "1.2.3"` (package.json)
- `__version__ = "1.2.3"` (a Python module)
- a file holding only `1.2.3` (VERSION)

Versions are always three numbers, `MAJOR.MINOR.PATCH`.

**The changelog** must look like this. Create it if the project has none:

```markdown
# Changelog

## [Unreleased]

### Added
- Something new, written for the people who use the project.

### Changed
- Something that works differently now.

### Fixed
- A bug that's gone.

## [1.2.0] - 2026-11-24

### Added
- ...
```

- Keep `## [Unreleased]` at the top, exactly like that.
- Entries go under `### Added`, `### Changed`, `### Fixed`, `### Removed`,
  `### Security` or `### Deprecated`. Each entry is a line starting with `- `.
- Subsections named in `changelog.keep_unreleased` (default `Planned`) stay
  under Unreleased when a release is made; everything else moves under the
  new `## [x.y.z] - YYYY-MM-DD` heading.
- **Add an entry every time you change the project.** Release refuses to run
  when Unreleased has no entries, and it can't tell whether you forgot one.

## The project file

`.runner/project.toml`, every field (all optional; the defaults are shown):

```toml
[project]
name = "<folder name>"        # notifications and launcher names: "<name> Push"
main_branch = "main"          # Merge fast-forwards into it; Release runs from it
remote = "origin"             # Push and Release push here

[version]
file = ""                     # where the version is; empty = no Release
also = []                     # other files stating the same version
tag = "{version}"             # release tag format; must contain {version}, e.g. "v{version}"

[changelog]
file = ""                     # Keep a Changelog file; empty = no Release
keep_unreleased = ["Planned"] # subsections that stay under Unreleased

[commands]                    # shell commands, run from the project folder; empty = skip
lint = ""
test = ""
build = ""

[release]
publishes = false             # true if pushing a release tag publishes something (CI)
```

Set `publishes = true` when a pushed tag starts something public, such as a
GitHub Actions release. Push and Release then ask the user before pushing a
new release tag.

Commands run with `bash -c` in the project's folder, with no terminal. Use
paths that work from there (`.venv/bin/python -m pytest -q`, `npm test`,
`./scripts/build.sh`), and nothing that waits for typed input.

## What the scripts do

| Script | Does | Stops, changing nothing, when |
| --- | --- | --- |
| `build` | Runs `commands.build`. | There is no build command. |
| `merge` | Fast-forwards `main_branch` to the current branch, then switches to it. Never pushes. | On main already; uncommitted changes; nothing new on the branch; main has commits the branch lacks (rebase first). |
| `push` | Pushes the current branch and any new release tags on it. | The remote has commits you don't (pull first). With `publishes`, asks before pushing a new release tag. |
| `release` | Asks patch, minor or major; runs lint then test; writes the version into every version file; moves Unreleased entries under the new version and today's date; commits `release: x.y.z`; tags it; asks before pushing. | Not on main; uncommitted changes; behind the remote; no Unreleased entries; the tag exists; lint or tests fail. |

Each run ends with a notification (done, stopped with the reason, or failed
with the step) and is logged, replacing the previous log, at
`~/Library/Logs/Runner/scripts/<name>/<script>.log` on macOS. Read that log
when the user says a launcher didn't work.

You may run the scripts yourself in a terminal when the user asks:
`runner project push`, `runner project merge`, `runner project build`,
`runner project release --patch --no-publish` (the flags skip its two
questions; `--publish` pushes without asking). They need bash, so they work
on macOS and Linux only.

## Other commands

| Command | Prints |
| --- | --- |
| `runner project version` | The project's current version (and checks the version files agree). |
| `runner project bump patch --dry-run` | The version a patch release would make, after checking the changelog. Without `--dry-run` it writes it; Release does that for you. |
| `runner project tag 1.2.3` | The tag that version gets. |

Exit status: 0 done, 1 refused or failed (the reason is on stderr), 2 the
command line was wrong.

## Things that catch people out

- **The changelog is the release notes.** Keep it current as you work, in
  words for the project's users, not commit messages.
- **Release needs a clean main.** Commit (or ask the user to commit) before
  telling them to click Release.
- **Merge only fast-forwards.** If main has moved on, rebase the branch first;
  the script won't create merge commits or resolve conflicts.
- **The launchers call Runner's own copy of the scripts**, so updating Runner
  updates every project's scripts. Don't copy the scripts into the project.
- **Don't run `launchers` without `--as`.** The default source `cli` is shared;
  use your own name so you can update or remove what you made later
  (`runner ctl --as <name> launcher list --mine`).
