#!/bin/bash
set -euo pipefail

# Build Runner.app and Runner.dmg for macOS, and optionally install it here.
#
# Usage:
#   ./scripts/build-mac.sh               test, then build dist/Runner.app and dist/Runner.dmg
#   ./scripts/build-mac.sh --deploy      also replace /Applications/Runner.app and start it
#   ./scripts/build-mac.sh --skip-tests  build without running pytest first
#
# Works from any folder. The version comes from pyproject.toml; runner.spec
# reads the same value for the bundle's Info.plist.

DEPLOY=0
RUN_TESTS=1
for arg in "$@"; do
  case "$arg" in
    --deploy) DEPLOY=1 ;;
    --skip-tests) RUN_TESTS=0 ;;
    -h|--help)
      sed -n '4,12p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Unknown option: $arg (try --help)" >&2
      exit 2
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"
APP="$PROJECT_ROOT/dist/Runner.app"
DMG="$PROJECT_ROOT/dist/Runner.dmg"
INSTALLED="/Applications/Runner.app"

# runner.spec and PyInstaller use paths relative to the project root.
cd "$PROJECT_ROOT"

# A Qt path left in the shell (for example one pointing into an installed
# Runner.app) makes the venv load a second copy of Qt, which aborts.
for var in QT_PLUGIN_PATH QT_QPA_PLATFORM_PLUGIN_PATH; do
  if [ -n "${!var:-}" ]; then
    echo "==> Ignoring $var=${!var} from your shell"
    unset "$var"
  fi
done

if [ ! -x "$VENV_DIR/bin/python" ]; then
  echo "ERROR: Project venv not found at $VENV_DIR" >&2
  echo "Create it first, from $PROJECT_ROOT:" >&2
  echo "  python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'" >&2
  exit 1
fi
# Use the venv's Python directly, whatever venv the calling shell has active.
PY="$VENV_DIR/bin/python"

VERSION="$(sed -n 's/^version[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' pyproject.toml | head -n 1)"
if [ -z "$VERSION" ]; then
  echo "ERROR: no version found in pyproject.toml" >&2
  exit 1
fi
PKG_VERSION="$("$PY" -c 'import sys; sys.path.insert(0, "src"); import runner; print(runner.__version__)')"
if [ "$PKG_VERSION" != "$VERSION" ]; then
  echo "ERROR: pyproject.toml says $VERSION but src/runner/__init__.py says $PKG_VERSION" >&2
  exit 1
fi

echo "==> Runner $VERSION"
echo "==> Python: $PY ($("$PY" --version 2>&1))"
echo "==> PyInstaller: $("$PY" -m PyInstaller --version)"

if [ "$RUN_TESTS" -eq 1 ]; then
  echo "==> Running tests (some briefly open windows)..."
  # The GUI tests use the normal macOS display. Set QT_QPA_PLATFORM yourself
  # to override, for example on a headless machine.
  # --capture=sys lets Qt's own error messages through. A Qt abort kills the
  # process, and pytest's default capture would lose the reason.
  "$PY" -m pytest -q --capture=sys
fi

echo "==> Building Runner.app..."
# The spec strips unused Qt modules, plugins, and translations, and writes
# Info.plist (LSUIElement, names, version, bundle id).
"$PY" -m PyInstaller --clean --noconfirm runner.spec

if [ ! -d "$APP" ]; then
  echo "ERROR: PyInstaller finished but $APP is missing" >&2
  exit 1
fi

echo "==> Ad-hoc signing (lets the app run locally; not a Developer ID signature)..."
codesign --force --deep --sign - "$APP"

echo "==> Creating $DMG..."
hdiutil create -volname "Runner" -srcfolder "$APP" -ov -format UDZO "$DMG" >/dev/null

echo "==> Built:"
ls -lh "$DMG"
du -sh "$APP"

if [ "$DEPLOY" -eq 0 ]; then
  echo
  echo "To install on this Mac: ./scripts/build-mac.sh --deploy"
  echo "To give someone else: send dist/Runner.dmg."
  exit 0
fi

# ------------------------------------------------------------------ deploy

echo "==> Deploying to $INSTALLED..."

# Ask the installed copy to quit, so it saves its arrow position, then wait.
if pgrep -f "$INSTALLED/Contents/MacOS/" >/dev/null; then
  echo "    Quitting the running Runner..."
  # The installed copy may be an older build with the misspelled bundle id.
  for bundle_id in com.dougie.runner com.douglie.runner; do
    osascript -e "tell application id \"$bundle_id\" to quit" >/dev/null 2>&1 || true
  done
  for _ in $(seq 1 50); do
    pgrep -f "$INSTALLED/Contents/MacOS/" >/dev/null || break
    sleep 0.1
  done
  if pgrep -f "$INSTALLED/Contents/MacOS/" >/dev/null; then
    echo "    Still running after 5 s; stopping it."
    pkill -f "$INSTALLED/Contents/MacOS/" || true
    sleep 1
  fi
fi

# Only one Runner runs at a time. A copy started from the source tree would
# make the new app exit straight away, so say so instead of silently failing.
if pgrep -f "python.*-m runner|runner/main.py|\.venv/bin/runner" >/dev/null; then
  echo "WARNING: a Runner started from the source tree is running." >&2
  echo "         Quit it (right-click the arrow > Exit) or the installed app will not open." >&2
fi

# Copy beside the old app first, then swap, so a failed copy leaves the old one in place.
STAGING="/Applications/.Runner.app.new"
rm -rf "$STAGING"
ditto "$APP" "$STAGING"
rm -rf "$INSTALLED"
mv "$STAGING" "$INSTALLED"

echo "==> Starting $INSTALLED..."
open "$INSTALLED"
echo "==> Deployed Runner $VERSION."
