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

echo "==> Building Runner macOS bundle..."

# Canonical spec excludes unused Qt modules/plugins/translations (PDF, QML,
# Virtual Keyboard, SVG, extra image codecs) so the .app stays Widgets-only.
pyinstaller --clean --noconfirm "$PROJECT_ROOT/runner.spec"

APP="dist/Runner.app"

echo "==> Making it a background/agent app (no Dock icon) and setting nice names..."
/usr/libexec/PlistBuddy -c "Add :LSUIElement bool true" "$APP/Contents/Info.plist" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Set :LSUIElement true" "$APP/Contents/Info.plist"

/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName 'Runner'" "$APP/Contents/Info.plist" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Set :CFBundleName 'Runner'" "$APP/Contents/Info.plist" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString 1.0.1" "$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleVersion 1.0.1" "$APP/Contents/Info.plist"

# Use a stable bundle identifier (change if you want)
BUNDLE_ID="com.douglie.runner"
 /usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string $BUNDLE_ID" "$APP/Contents/Info.plist" 2>/dev/null || \
 /usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier $BUNDLE_ID" "$APP/Contents/Info.plist"

echo "==> Ad-hoc code signing the bundle (helps with local Gatekeeper)..."
codesign --force --deep --sign - "$APP" 2>&1 | cat || echo "Signing warning (non-fatal for local use)"

echo "==> Creating distributable .dmg..."
rm -f "dist/Runner.dmg"
hdiutil create -volname "Runner" \
  -srcfolder "$APP" \
  -ov -format UDZO "dist/Runner.dmg"

echo "==> Done."
ls -lh "dist/Runner.dmg" "$APP"
echo
echo "To 'install' on this machine for testing: cp -R '$APP' /Applications/"
echo "Client: give them the .dmg (drag app to Applications inside the dmg)."
