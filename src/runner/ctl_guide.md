# runner ctl: a guide for LLMs and scripts

Runner is a small always-on-top launcher. Its user starts programs, scripts,
files and URLs from it, singly (a *launcher*) or several in order (an
*execute group*). `runner ctl` lets you add, change and delete launchers,
groups and containers from outside Runner, so the user can then start them
with a click.

Print this guide any time with `runner ctl guide`.

**Setting up a code project** with Build, Merge, Push and Release launchers?
That has its own guide and commands: `runner project guide`. Use this guide
for launchers and groups in general.

## Before you start

1. **Find the command.** Try these in order and use the first that works:
   - `runner ctl ping`, if `runner` is on the PATH
   - `/Applications/Runner.app/Contents/MacOS/Runner ctl ping`, the Mac app
   - `.venv/bin/runner-ctl ping`, in a development checkout of Runner

   `Runner 1.x.y is answering.` means you are talking to the running app.
   `Runner isn't running.` is fine too: changes then go straight into its
   config file, and Runner picks them up when it starts.
2. **Always pass `--as <your name>`**, such as `--as claude`, on every
   command. That is the *source* your changes are made as. Only the same
   source can change or delete them later. The default is `cli`, which is
   shared by everything that forgets `--as`, so don't rely on it.
3. **Look before you add.** `runner ctl --as claude launcher list --mine`
   shows what you made before. Use `upsert` instead of `add` so running the
   same setup twice updates instead of duplicating.

## The rules

Runner enforces these. A refused request prints the reason and exits 1.

- **You can only change what your source made.** Anything the user made in
  Runner, or another source made, is read-only to you. You can still *use*
  it: put the user's launchers in your groups by name.
- **You can't run anything.** There is no run command. The user starts
  launchers and groups themselves.
- **No administrator rights.** `run_as_admin` can't be set from outside.
- **Only the user schedules.** You can give a group dates (`--date`), but
  only the user can turn its Schedule switch on, in Runner. Once a group is
  scheduled you can't change it, or the command, args or folder of any
  launcher it runs, until the user turns the schedule off.
- **Not while Runner has a window open.** Changes are refused while one of
  Runner's own windows (an edit screen, a manager) is open, because it would
  save over them. Ask the user to close it and try again. Reading still works.

## Commands

    runner ctl [--as SOURCE] [--json] <kind> <verb> [options]

Kinds: `launcher`, `group` (an execute group), `container` (a container
group: a submenu that lists launchers and doesn't run them).
Also `ping`, `guide` and `raw`.

| Verb | What it does |
| --- | --- |
| `list [--mine \| --source NAME]` | One line per item; `--mine` is what `--as` made |
| `get REF` | One item, as JSON |
| `add [fields]` | Make a new one. Needs `--name` (and `--command` for a launcher) |
| `update REF [fields]` | Change one of yours. Only the fields you give change |
| `upsert --name NAME [fields]` | Change yours with that name, or add it |
| `delete REF` | Delete one of yours. A launcher also leaves every group and container |

`REF` is an item's id or its name. Names match whatever the case. If two
items share a name you get an error listing their ids: use an id.

`--json` (before the kind) prints the full reply, which is best for reading
results back. Add `--help` after any command for its options.

### Launcher fields

| Option | JSON field | Meaning |
| --- | --- | --- |
| `--name` | `name` | What the user sees |
| `--command` | `command` | A program, script, `.app`, file or URL. Use an absolute path |
| `--args` | `args` | Arguments, as one string, split like a shell would |
| `--cwd` | `working_dir` | Folder to start in. `--cwd ""` clears it |
| `--show-in-main` / `--no-show-in-main` | `show_in_main` | On Runner's main list (new launchers: yes). Off, it still runs in its groups |
| `--show-console` / `--no-show-console` | `show_console` | Windows only: show a console window |

### Group fields

| Option | JSON field | Meaning |
| --- | --- | --- |
| `--name` | `name` | What the user sees |
| `--launcher REF` | `launchers` | Launchers it runs, in order. Repeat the option for more. Giving any replaces the whole list |
| `--concurrent REF` | `{"ref": REF, "concurrent": true}` | Like `--launcher`, but starts at the same time as the one before |
| `--clear-launchers` | `"launchers": []` | No launchers |
| `--show-contents` / `--no-show-contents` | `show_contents` | Hovering the group lists its launchers |
| `--click-runs` / `--no-click-runs` | `click_runs` | Once scheduled: a click in the Schedules list runs it (instead of opening it to edit) |
| `--date WHEN` | `schedule` | A date it runs on. Repeat for more. Giving any replaces all its dates |
| `--every INTERVAL` | (in each date) | How often the `--date` just before it repeats |
| `--clear-dates` | `"schedule": []` | No dates |

Containers take `--name`, `--launcher` and `--clear-launchers` only.

`--date` reads `2026-11-25 09:00`, `25/11/2026 9am` (day first),
`25 Nov 2026 18:30`, `Wednesday 25 November 2026 · 09:00`. **Always include
the time**: a missing part is taken from now, so `--date "25 Nov"` means
25 November at the current time of day.

`--every` reads `1 week`, `2 days`, `1d 12h`, `1 month 2 weeks`, `30 min`.
Each unit stops where the next one starts: at most 99 months, 3 weeks,
6 days, 23 hours, 59 minutes. Write 4 weeks as 1 month. A date with no
`--every` runs once.

`--data JSON` merges extra JSON fields in last, for anything the options
don't cover.

## Examples

Make a launcher for a script and put it in a group, safe to run again:

    runner ctl --as claude launcher upsert --name "Build & deploy" \
        --command /Users/me/Projects/app/scripts/deploy.sh --args=--prod \
        --cwd /Users/me/Projects/app --no-show-in-main
    runner ctl --as claude group upsert --name "Release" --launcher "Build & deploy"
    runner ctl --as claude --json group get Release

Open several things together, the second at the same time as the first:

    runner ctl --as claude launcher upsert --name News --command https://news.example.com
    runner ctl --as claude group upsert --name "Morning" \
        --launcher Mail --concurrent Calendar --launcher News

`--launcher` takes launchers that already exist, the user's or yours.

Give a group a weekly date for the user to switch on:

    runner ctl --as claude group update Release --date "2026-12-01 09:00" --every "1 week"

Then tell the user: "Open Release in Runner and turn on its Schedule switch."

Clean up everything you made:

    runner ctl --as claude --json launcher list --mine
    runner ctl --as claude group delete Release
    runner ctl --as claude launcher delete "Build & deploy"

## Things that catch people out

- **An argument value that starts with `-`** must be joined with `=`:
  `--args=--deploy`, not `--args --deploy`.
- **Scripts run without a terminal on macOS and Linux.** Their output isn't
  shown anywhere. A script must be executable (`chmod +x`) with a `#!` line,
  or use the interpreter as the command: `--command /usr/bin/python3
  --args "/path/tool.py"`. Write to a log file if the user needs to see output.
- **Use absolute paths** for `--command` and `--cwd`. `~` works too.
- **New launchers appear on the user's main list.** Pass `--no-show-in-main`
  for ones that only make sense inside a group.
- **Giving `--launcher` or `--date` replaces the whole list**, it doesn't add
  to it. Read the group first (`--json group get`) and give the full list.
- **The Windows `.exe` prints nothing**, because it has no console. On
  Windows use a development install (`runner-ctl`).

## Exit status

| Code | Meaning |
| --- | --- |
| 0 | Done |
| 1 | Runner refused it, or isn't running (`ping`). The reason is on stderr |
| 2 | The command line was wrong |
| 3 | Runner is running but didn't answer: probably a version from before `runner ctl`. Ask the user to update Runner |

## Raw JSON requests

`runner ctl raw '<json>'` (or `raw -` to read stdin) sends one request as it
is; `--as` fills in `source` if the request has none. The reply is
`{"ok": true, "result": ...}` or `{"ok": false, "error": "..."}`.

    {"op": "ping"}
    {"op": "launcher.list", "filter": {"source": "claude"}}
    {"op": "group.get", "ref": "Release"}
    {"op": "launcher.add", "source": "claude",
     "data": {"name": "Tool", "command": "/usr/local/bin/tool", "args": "--fast",
              "working_dir": null, "show_in_main": false}}
    {"op": "group.upsert", "source": "claude",
     "data": {"name": "Release",
              "launchers": ["Build & deploy", {"ref": "Notify", "concurrent": true}],
              "show_contents": false, "click_runs": false,
              "schedule": [{"start": "2026-12-01T09:00", "weeks": 1}]}}
    {"op": "container.update", "source": "claude", "ref": "Tools",
     "data": {"launchers": ["Tool"]}}
    {"op": "group.delete", "source": "claude", "ref": "Release"}

Ops are `<kind>.<verb>` with the verbs above. `schedule` entries have
`start` (`YYYY-MM-DDTHH:MM`, local time) and any of `months`, `weeks`,
`days`, `hours`, `minutes`. In replies, launchers also list the `groups` and
`containers` they are in, and every item has its `id` and `source` (`null`
for items the user made in Runner).
