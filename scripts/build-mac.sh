#!/bin/bash
set -euo pipefail

# Build a macOS .app bundle + .dmg for client distribution.
# Run from repo root after `source .venv/bin/activate`

echo "==> Building Script Runner macOS bundle..."

pyinstaller --clean --noconfirm \
  --name "Script Runner" \
  --windowed \
  --onedir \
  src/script_runner/main.py

APP="dist/Script Runner.app"

echo "==> Making it a background/agent app (no Dock icon)..."
/usr/libexec/PlistBuddy -c "Add :LSUIElement bool true" "$APP/Contents/Info.plist" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Set :LSUIElement true" "$APP/Contents/Info.plist"

echo "==> Creating distributable .dmg..."
rm -f "dist/Script-Runner-mac.dmg"
hdiutil create -volname "Script Runner" \
  -srcfolder "$APP" \
  -ov -format UDZO "dist/Script-Runner-mac.dmg"

echo "==> Done."
ls -lh "dist/Script-Runner-mac.dmg" "$APP"
echo
echo "To 'install' on this machine for testing: cp -R '$APP' /Applications/"
echo "Client: give them the .dmg (drag app to Applications inside the dmg)."
