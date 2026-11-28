#!/bin/bash
set -euo pipefail

# Install dist/Runner.app into /Applications and start it, replacing the
# copy that is there. Quits a running installed Runner first, so it saves
# its arrow position. Builds nothing: run scripts/build-mac.sh first, or
# scripts/deploy.sh, which builds only when the build is out of date.
#
# Usage:
#   ./scripts/install-mac.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
APP="$PROJECT_ROOT/dist/Runner.app"
INSTALLED="/Applications/Runner.app"

if [ ! -d "$APP" ]; then
  echo "ERROR: no build at $APP. Run ./scripts/build-mac.sh first." >&2
  exit 1
fi
VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$APP/Contents/Info.plist" 2>/dev/null || echo unknown)"

echo "==> Deploying to $INSTALLED..."

# The installed Runner's process ids, by the program each one runs.
# pgrep on macOS leaves out its own ancestors unless given -a. Started from
# a Runner launcher, Runner is this script's parent, so without -a it looked
# absent and was never quit. Matching the program, not the command line,
# keeps -a from also catching a shell whose command mentions the path.
running_pids() {
  local pid
  for pid in $(pgrep -a -x Runner || true); do
    case "$(ps -o comm= -p "$pid" 2>/dev/null)" in
      "$INSTALLED"/Contents/MacOS/*) echo "$pid" ;;
    esac
  done
}

# Ask the installed copy to quit, so it saves its arrow position, then wait.
OLD_PIDS="$(running_pids)"
if [ -n "$OLD_PIDS" ]; then
  echo "    Quitting the running Runner ($(echo $OLD_PIDS))..."
  # The installed copy may be an older build with the misspelled bundle id.
  for bundle_id in com.dougie.runner com.douglie.runner; do
    osascript -e "tell application id \"$bundle_id\" to quit" >/dev/null 2>&1 || true
  done
  for _ in $(seq 1 50); do
    [ -n "$(running_pids)" ] || break
    sleep 0.1
  done
  if [ -n "$(running_pids)" ]; then
    echo "    Still running after 5 s; stopping it."
    kill $(running_pids) 2>/dev/null || true
    sleep 1
  fi
  if [ -n "$(running_pids)" ]; then
    echo "ERROR: Runner is still running, so the app was not replaced." >&2
    exit 1
  fi
fi

# Only one Runner runs at a time. A copy started from the source tree would
# make the new app exit straight away, so say so instead of silently failing.
if pgrep -a -f "python.*-m runner|runner/main.py|\.venv/bin/runner" >/dev/null; then
  echo "WARNING: a Runner started from the source tree is running." >&2
  echo "         Quit it (right-click the arrow > Exit) or the installed app will not open." >&2
fi

# Copy beside the old app first, then swap with rollback if mv fails.
STAGING="/Applications/.Runner.app.new"
BACKUP="/Applications/.Runner.app.old"
rm -rf "$STAGING" "$BACKUP"
ditto "$APP" "$STAGING"
if [ -d "$INSTALLED" ]; then
  mv "$INSTALLED" "$BACKUP"
fi
if ! mv "$STAGING" "$INSTALLED"; then
  echo "ERROR: could not move new Runner.app into place; restoring previous copy." >&2
  if [ -d "$BACKUP" ]; then
    mv "$BACKUP" "$INSTALLED"
  fi
  rm -rf "$STAGING"
  exit 1
fi
rm -rf "$BACKUP"

echo "==> Starting $INSTALLED..."
# open passes this shell's environment on. QT_QPA_PLATFORM=offscreen (set
# to run the tests without windows) would start Runner with nothing on screen.
env -u QT_QPA_PLATFORM open "$INSTALLED"
# Check that a new Runner is up, not an old one brought to the front.
for _ in $(seq 1 100); do
  NEW_PIDS="$(running_pids)"
  [ -z "$NEW_PIDS" ] || break
  sleep 0.1
done
if [ -z "$NEW_PIDS" ]; then
  echo "ERROR: the new Runner did not start within 10 s." >&2
  exit 1
fi
echo "==> Deployed Runner $VERSION (pid $(echo $NEW_PIDS))."
