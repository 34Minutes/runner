# Runner Help

Runner is the small arrow that floats above your other windows. Hover it to
open your launchers, and click one to start it.

## Features

| Feature | What it does |
| --- | --- |
| **Launchers** | Start an app, script, file, folder or web page with one click. Right-click the arrow → **Add Launcher…**; right-click a row to **Edit** or **Delete** it. |
| **The arrow** | Hover to open the list. Drag it to move it, or drag an edge to resize it. **Reset Position and Size** in the tray menu brings it back. |
| **Filter and keys** | Type in the filter box to narrow the list. Arrow keys move, **Enter** starts, **Esc** clears or closes. Drag rows to reorder them. |
| **Execute groups** | Start several launchers one after another, or together with **Concurrent**. Right-click → **Execute Groups**. |
| **Container groups** | Folders in the list: hover one (**›**) to see its launchers. Right-click → **Container Groups**. |
| **Schedules** | An execute group that runs by itself on the dates you set, with optional repeats. They only run while Runner is open; missed runs are skipped. Right-click → **Schedules**. |
| **Manage Launchers…** | Edit, delete and reorder all your launchers in one window. |
| **Look and feel** | Opacity, how fast lists fade, colour scheme (Dark, Medium, Bright), pinning the list open, and the greeting hint. All of these are in the right-click menu. |
| **Script templates** | Ready-made build, merge, push, release and test scripts to copy into a code project (`runner template`). |
| **Outside control** | Scripts and LLMs can add launchers and groups with `runner ctl`. They can't run anything; only you can. |

## Good to know

- **Scripts** start without a Terminal window, so you won't see their output.
  A script must be executable (`chmod +x`) and start with a `#!` line. The
  templates write a log and show a notification.
- **Settings** are in `~/Library/Application Support/Runner/config.json`
  (Windows: `%APPDATA%\Runner\config.json`). After editing it by hand, choose
  **Reload Config** from the tray menu.
- **Opening Runner again** brings the running Runner forward; it never
  starts a second copy.

## For LLMs and scripts

First put `runner` on your PATH:

```
mkdir -p ~/.local/bin && ln -sf /Applications/Runner.app/Contents/MacOS/Runner ~/.local/bin/runner
```

Then paste this into your LLM's standing instructions (for Claude Code,
`~/.claude/CLAUDE.md`):

```
## Runner (my desktop launcher)
When I ask for a launcher, button or one-click way to run something, make it
in Runner. Commands (if `runner` isn't found, use
/Applications/Runner.app/Contents/MacOS/Runner):
  runner ctl ping                              is Runner answering?
  runner ctl guide                             how to make launchers and groups; read it first
  runner ctl --as claude launcher list --mine  what you made before
  runner template list                         script templates: build, merge, push, release, test-once
  runner template show NAME                    read a template
  runner template copy NAME... --to DIR        copy templates into a project, then edit their settings
Always pass --as claude, use upsert and absolute paths. You can't run what you
make: tell me its name and where it is in Runner.
```
