#!/bin/bash
set -euo pipefail

# Build Runner.app and Runner.dmg for macOS, and optionally install it here.
#
# Usage:
#   ./scripts/build-mac.sh               test, then build dist/Runner.app and dist/Runner.dmg
#   ./scripts/build-mac.sh --deploy      also replace /Applications/Runner.app and start it
#   ./scripts/build-mac.sh --skip-tests  build without the lint check and tests first
#
# Works from any folder. The version comes from pyproject.toml; runner.spec
# reads the same value for the bundle's Info.plist. scripts/build.sh
# (the Runner Build launcher) runs it with a log and a notification.
# --deploy hands the new build to scripts/install-mac.sh; scripts/deploy.sh
# (the Runner Deploy launcher) installs without rebuilding when it can.

DEPLOY=0
RUN_TESTS=1
for arg in "$@"; do
  case "$arg" in
    --deploy) DEPLOY=1 ;;
    --skip-tests) RUN_TESTS=0 ;;
    -h|--help)
      sed -n '4,14p' "$0" | sed 's/^# \{0,1\}//'
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

VERSION="$("$PY" scripts/check_version.py)"

echo "==> Runner $VERSION"
echo "==> Python: $PY ($("$PY" --version 2>&1))"
echo "==> PyInstaller: $("$PY" -m PyInstaller --version)"

if [ "$RUN_TESTS" -eq 1 ]; then
  # Lint and tests, one run at a time, and skipped when this code already
  # passed (RUNNER_TESTS_FORCE=1 runs them anyway). The GUI tests use the
  # normal macOS display. Set QT_QPA_PLATFORM yourself to override, for
  # example on a headless machine.
  "$PY" scripts/run_tests.py
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
# The disk image holds the app, its license, and the third-party notices.
DMG_DIR="$PROJECT_ROOT/build/dmg"
rm -rf "$DMG_DIR"
mkdir -p "$DMG_DIR"
ditto "$APP" "$DMG_DIR/Runner.app"
cp LICENSE THIRD-PARTY-NOTICES.txt "$DMG_DIR/"
hdiutil create -volname "Runner" -srcfolder "$DMG_DIR" -ov -format UDZO "$DMG" >/dev/null

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
"$SCRIPT_DIR/install-mac.sh"
