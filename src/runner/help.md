# Runner Help

Runner is the small arrow that floats above your other windows. Hover it, and
a list of your **launchers** opens: click one to start a program, a script, a
file, a folder or a web page. Everything else in Runner is a way to group,
order or time those launchers.

**Contents**

1. Getting started
2. Launchers
3. Execute groups: several launchers in one click
4. Container groups: folders in the list
5. Schedules: run a group at set times
6. The arrow's right-click menu
7. Tips and troubleshooting
8. Using Runner from other projects, scripts and LLMs

---

## 1. Getting started

1. **Hover the arrow.** Your launcher list opens. The first time, it has a
   few examples: Calculator, Calendar, a web browser and so on.
2. **Click a launcher** to start it. The list closes.
3. **Right-click the arrow** and choose **Add Launcher…** to add your own.
4. **Drag the arrow** to move it. **Drag an edge or corner** to resize it.
   Runner remembers both.
5. **Right-click a row** in the list for **Edit** or **Delete**.

If you lose the arrow, choose **Reset Position and Size** from the tray icon's
menu. It puts the arrow back near the top-left of the screen.

---

## 2. Launchers

A launcher is one thing to start. **Add Launcher…** (or **Edit**) asks for:

| Field | What to put there |
| --- | --- |
| **Name** | What the list shows. |
| **Command / Path** | What to start: an app (on a Mac, `Safari` or `/Applications/Safari.app`), a program, a script, a file, a folder, or a web address like `https://example.com`. **Browse…** picks one. |
| **Parameters / Args** | Extra words for the command, for example a file to open or `--deploy`. Quote anything with spaces in it. |
| **Working directory** | The folder the command starts in. Leave it empty for your home folder. |
| **Include in dropdown list** | Off hides it from the main list. It still works inside groups. |

Below those, tick the execute groups and container groups it belongs to.

**In the list:**

- **Drag a row** to put it in a new order.
- **Type in the filter box** at the top to narrow the list by name or command.
- **Arrow keys** move the highlight, **Enter** starts the highlighted launcher,
  **Esc** clears the filter or closes the list.
- **Manage Launchers…** on the right-click menu edits, deletes and orders them
  all in one window.

**Scripts:** Runner starts a script with no Terminal window, so anything it
prints isn't shown. The script must be executable (`chmod +x script.sh`) and
start with a `#!` line, such as `#!/bin/bash`. If you need to see what it did,
have it write a log file or show a notification.

---

## 3. Execute groups: several launchers in one click

An execute group starts its launchers one after another, in order. Use one to
open everything for a task at once: your mail, calendar and notes, say.

- **Make one:** right-click the arrow → **Execute Groups** → **Add…**. Name
  it, then click launchers to include them. They run in the order shown; drag
  them to change it.
- **Concurrent** on a row starts that launcher at the same time as the one
  above it, instead of after it.
- **Only in Groups** keeps a launcher off the main list; it still runs here.
- **Run one:** right-click the arrow → **Execute Groups** → **Show**, then click
  the group. Or turn on **Show execute groups** in the right-click menu, and the
  groups list opens beside your launchers whenever you hover the arrow.
- **Show group contents** on a group lists its launchers when you hover it, so
  you can start just one of them.

---

## 4. Container groups: folders in the list

A container group is a folder in your launcher list. It doesn't run anything:
hover it (it has a **›**) and its launchers open beside it, then click one.

- **Make one:** right-click the arrow → **Container Groups** → **Add…**, name it,
  and click the launchers it holds.
- **Only in Container Group** keeps a launcher out of the main list, so it only
  appears inside the folder.
- Drag a launcher from the main list onto a container to move it in.

---

## 5. Schedules: run a group at set times

A schedule is an execute group that runs by itself on the dates you give it.

1. Right-click the arrow → **Schedules** → **Add…**. (Or open any execute group
   and turn on its **Schedule** switch.)
2. Press **+** and turn the dial's rings to the date and time. Press the dial's
   silver centre to choose it. The **Minutes** switch hides the minute ring;
   **Now** spins the dial back to now. You can also click the written-out date
   under the dial, type a date like `5 March 2027 18:05`, and press Enter.
3. Press the button beside the date to choose how often it repeats, on the
   rollers, then press **Select**. Or press **Don't repeat**.
4. Press **Save**.

Schedules run only while Runner is open. A run missed while Runner was closed,
or the computer was asleep, is skipped. Scheduled groups appear only under
**Schedules**, with their next run time. Clicking one opens it for editing,
unless you turn on **Clicking it in the Schedules list runs it now** in the
group.

---

## 6. The arrow's right-click menu

| Item | What it does |
| --- | --- |
| **Add Launcher…**, **Manage Launchers…** | Add one, or edit them all. |
| **Reset Position and Size** | Puts the arrow back to its starting place and size. |
| **Schedules**, **Execute Groups**, **Container Groups** | Each has **Show** (open that list), **Add…** and **Manage…**. |
| **Pin dropdown open** | Keeps the list open instead of closing when the pointer leaves. |
| **Show filter box in dropdown** | The filter box at the top of the list. |
| **Show greeting message** | The flashing hint about resizing and moving the arrow. |
| **Show execute groups** | Opens the execute groups list beside your launchers on hover. |
| **Opacity** | How solid the arrow is. |
| **Decay rate** | How quickly a list fades after the pointer leaves it. |
| **Color Schemes** | Dark, Medium or Bright. |
| **Help** | This page. |
| **Exit** | Quits Runner. |

---

## 7. Tips and troubleshooting

- **Nothing happens when I click a launcher.** Check the command with **Edit**.
  For a script: is it executable, with a `#!` line? Does it need a **Working
  directory**? Remember there is no Terminal window to show its output.
- **Runner is already running** when you open it again: the arrow is
  brought forward instead of starting a second copy.
- **Your settings and launchers** are in one file:
  `~/Library/Application Support/Runner/config.json` on a Mac,
  `%APPDATA%\Runner\config.json` on Windows. After editing it by hand, choose
  **Reload Config** from the tray icon's menu.
- **Windows stay on top.** Runner's own windows sit above the arrow and the
  lists, so they are never hidden behind them.

---

## 8. Using Runner from other projects, scripts and LLMs

Runner can be set up from the command line, so a script or an LLM coding
assistant (Claude, for example) can make launchers for you. There are two
parts:

- **`runner ctl`** adds, changes and deletes launchers, execute groups and
  container groups. Anything can use it: "make me a launcher for this script".
- **`runner project`** gives a code project four ready-made launchers:
  **Build**, **Merge**, **Push** and **Release**, run by scripts built into
  Runner. Each checks the project first, stops with the reason instead of
  guessing, keeps a log, and ends with a notification.

Neither can *run* anything. They only prepare launchers; you click them.

### 8.1 Once, on this Mac

**Put `runner` on your PATH**, so terminals and LLM tools can find it. In
Terminal:

```
mkdir -p ~/.local/bin && ln -sf /Applications/Runner.app/Contents/MacOS/Runner ~/.local/bin/runner
```

(If `~/.local/bin` isn't on your PATH, use `/usr/local/bin` instead.) Check it
with `runner ctl ping`. It should say `Runner x.y.z is answering`.

**Tell your LLM about Runner.** An LLM working in another project won't know
Runner exists. Paste this into its standing instructions. For Claude Code that
is `~/.claude/CLAUDE.md`; other tools have a "custom instructions" setting.

```
## Runner (my desktop launcher)
I use Runner, a launcher app, to start programs, scripts, files and URLs with one click.
When I ask for a launcher, a button, a shortcut or a one-click way to run something,
make it in Runner with `runner ctl` (if `runner` isn't found:
`/Applications/Runner.app/Contents/MacOS/Runner ctl`).
When I ask to set a project up for Runner, or for build, merge, push or release
launchers, follow `runner project guide`.
- Before your first use in a session, run `runner ctl guide` and follow it.
- Always pass `--as claude` (your own name), use `upsert`, and use absolute paths.
- You can't run what you make. Tell me its name and where to find it in Runner.
```

### 8.2 In each project: what the LLM (or you) does

Run these from inside the project's folder. Steps 1 to 5 are what an LLM does
when you ask it to "set this project up for Runner".

1. **Read the guide:** `runner project guide`. It explains everything below in
   full.
2. **Write the project file:** `runner project init`. This creates
   `.runner/project.toml` and fills in what it can detect: the main branch,
   the remote, where the version is written, the changelog, and test, lint and
   build commands.
3. **Fill in the rest:** open `.runner/project.toml`, check every line, and
   fill in anything left empty. Each line is explained in the file itself.
4. **Make sure the project has what the scripts read:**
   - a **git repository** with a main branch and a remote (for Push and Release)
   - a **version**, written in one file, such as `version = "1.0.0"` in
     `pyproject.toml` or `"version": "1.0.0"` in `package.json`, or a `VERSION`
     file (for Release)
   - a **changelog** in Keep a Changelog format (for Release): a
     `## [Unreleased]` section with `### Added`, `### Changed` and `### Fixed`
     underneath. Add an entry there every time something changes. Release
     turns those entries into the release notes, and refuses to release when
     there are none.
   - **commands** for lint, tests and build, if the project has them
5. **Check it:** `runner project check`. Fix anything marked **FIX** and check
   again until it says **Ready**.
6. **Make the launchers:** `runner project launchers --as claude`. This adds a
   container group called "*Project* Scripts" to your Runner, holding the
   project's launchers.

Then hover your arrow, open the container, and click.

### 8.3 What the four launchers do

| Launcher | What it does | It stops, changing nothing, when… |
| --- | --- | --- |
| **Build** | Runs the project's build command. | There's no build command. |
| **Merge** | Moves the main branch forward to the branch you're on (a fast-forward), then switches to main. Never pushes. | You're on main already, have uncommitted changes, the branch has nothing new, or main has moved on (rebase first). |
| **Push** | Pushes the branch you're on, and any new release tag. | The remote has commits you don't (pull first). If a release tag would publish something, it asks first. |
| **Release** | Asks patch, minor or major; runs lint and tests; writes the new version; moves the changelog's Unreleased entries under the new version and date; commits and tags; then asks before pushing. | You're not on main, have uncommitted changes, are behind the remote, or the changelog has nothing to release. A failing lint or test stops it before anything changes. |

Every run ends with a notification: done, stopped (with the reason), or failed
(with the step that failed). Each run is logged, replacing the last one, at:

```
~/Library/Logs/Runner/scripts/<Project>/<build|merge|push|release>.log
```

You can also run them in Terminal from the project's folder:
`runner project push`, `runner project merge`, `runner project release` and
`runner project build`. `runner project release --patch --no-publish` skips both
questions.

The scripts need bash, so they work on macOS and Linux, not Windows.

### 8.4 The rules for anything outside Runner

- Every change is made in the name of a **source** (`--as claude`). Only the
  same source can change or delete it later.
- Launchers and groups **you** made in Runner can't be changed from outside.
- Nothing from outside can **run** a launcher or a group, set one to run as
  administrator, or switch a **schedule** on. Those stay with you.
- While an editing window such as **Add Launcher** or **Manage Launchers** is
  open, outside changes are refused until you close it, so the window can't
  save over them. Help doesn't count: it can stay open.

For every command and option: `runner ctl guide` and `runner project guide`.
