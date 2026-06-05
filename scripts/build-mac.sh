#!/bin/bash
set -euo pipefail

# Build a macOS .app bundle + .dmg for client distribution.
# This script robustly activates the project's .venv (the one at the
# repo root), even if your current shell has a stale/different VIRTUAL_ENV
# active (common if you cd'd around and activated in a subdirectory).

# Resolve the project root reliably (two levels up from this script in scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"

if [ ! -f "$VENV_DIR/bin/activate" ]; then
  echo "ERROR: Project venv not found at $VENV_DIR/bin/activate"
  echo "Please create and populate it first (from the project root):"
  echo "  python -m venv .venv"
  echo "  source .venv/bin/activate"
  echo "  pip install -e '.[dev]'"
  exit 1
fi

echo "==> Activating project venv: $VENV_DIR"
# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

echo "==> Using Python from venv: $(which python)"
echo "==> PyInstaller version: $(python -m PyInstaller --version 2>/dev/null || echo 'not importable')"

echo "==> Building Script Runner macOS bundle..."

# Use scripts/launch.py as the entry point (bootstrap) + --paths src
# so that the app is started via the package (absolute imports work)
# and relative imports inside script_runner/* succeed.
pyinstaller --clean --noconfirm \
  --name "Script Runner" \
  --windowed \
  --onedir \
  --paths src \
  scripts/launch.py

APP="dist/Script Runner.app"

echo "==> Making it a background/agent app (no Dock icon) and setting nice names..."
/usr/libexec/PlistBuddy -c "Add :LSUIElement bool true" "$APP/Contents/Info.plist" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Set :LSUIElement true" "$APP/Contents/Info.plist"

/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName 'Script Runner'" "$APP/Contents/Info.plist" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Set :CFBundleName 'Script Runner'" "$APP/Contents/Info.plist" 2>/dev/null || true

# Use a stable bundle identifier (change if you want)
BUNDLE_ID="com.douglie.scriptrunner"
 /usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string $BUNDLE_ID" "$APP/Contents/Info.plist" 2>/dev/null || \
 /usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier $BUNDLE_ID" "$APP/Contents/Info.plist"

echo "==> Ad-hoc code signing the bundle (helps with local Gatekeeper)..."
codesign --force --deep --sign - "$APP" 2>&1 | cat || echo "Signing warning (non-fatal for local use)"

echo "==> Creating distributable .dmg..."
rm -f "dist/Script-Runner-mac.dmg"
hdiutil create -volname "Script Runner" \
  -srcfolder "$APP" \
  -ov -format UDZO "dist/Script-Runner-mac.dmg"

# Clean up the .spec file that PyInstaller generates next to the script
# (we don't want to commit build-time specs with spaces in the name)
rm -f "Script Runner.spec" 2>/dev/null || true

echo "==> Done."
ls -lh "dist/Script-Runner-mac.dmg" "$APP"
echo
echo "To 'install' on this machine for testing: cp -R '$APP' /Applications/"
echo "Client: give them the .dmg (drag app to Applications inside the dmg)."
