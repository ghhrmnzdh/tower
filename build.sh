#!/bin/bash
#
# build.sh — assemble "Tower.app" from src/.
#
# Compiles the native Swift menubar app (all src/*.swift together) and lays
# out the bundle:
#   Tower.app/
#     Contents/Info.plist
#     Contents/MacOS/tower              (compiled Swift binary — CFBundleExecutable)
#     Contents/Resources/towerd.py      (the daemon)
#     Contents/Resources/tower-tui.py
#     Contents/Resources/AppIcon.icns
#
# Requires: swiftc (Xcode or Command Line Tools) + python3 at runtime.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/src"
APP="$HERE/Tower.app"

echo "▸ cleaning bundle"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

echo "▸ compiling Swift sources (this can take ~20s)"
# -target matches Info.plist LSMinimumSystemVersion so the binary never
# silently requires the build machine's OS (latent bug in the old script).
swiftc -O -swift-version 5 \
  -target arm64-apple-macos14.0 \
  -o "$APP/Contents/MacOS/tower" \
  "$SRC"/*.swift \
  -framework AppKit -framework SwiftUI -framework Combine \
  -framework UserNotifications

echo "▸ copying resources"
cp "$SRC/Info.plist"     "$APP/Contents/Info.plist"
cp "$SRC/towerd.py"      "$APP/Contents/Resources/towerd.py"
cp "$SRC/tower-tui.py"   "$APP/Contents/Resources/tower-tui.py"
[ -f "$SRC/AppIcon.icns" ] && cp "$SRC/AppIcon.icns" "$APP/Contents/Resources/AppIcon.icns"
[ -f "$SRC/AppIcon.svg" ]  && cp "$SRC/AppIcon.svg"  "$APP/Contents/Resources/AppIcon.svg"
chmod +x "$APP/Contents/MacOS/tower"
chmod +x "$APP/Contents/Resources/towerd.py" "$APP/Contents/Resources/tower-tui.py"

echo "▸ ad-hoc code signing"
codesign --force --deep --sign - "$APP" 2>/dev/null || echo "  (codesign skipped)"

# Refresh LaunchServices / icon cache so Finder picks up changes immediately.
touch "$APP"

echo "✓ built: $APP"
