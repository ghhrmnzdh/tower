#!/bin/bash
#
# build.sh — assemble "Corral.app" from src/.
#
# Compiles the native Swift menubar app (all src/*.swift together) and lays
# out the bundle:
#   Corral.app/
#     Contents/Info.plist
#     Contents/MacOS/corral             (compiled Swift binary — CFBundleExecutable)
#     Contents/Resources/corrald.py     (the daemon)
#     Contents/Resources/corral-tui.py
#     Contents/Resources/AppIcon.icns
#     Contents/Resources/horses/*.svg   (design-system assets)
#
# Requires: swiftc (Xcode or Command Line Tools) + python3 at runtime.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/src"
APP="$HERE/Corral.app"

echo "▸ cleaning bundle"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

echo "▸ compiling Swift sources (this can take ~20s)"
# -target matches Info.plist LSMinimumSystemVersion so the binary never
# silently requires the build machine's OS (latent bug in the old script).
swiftc -O -swift-version 5 \
  -target arm64-apple-macos14.0 \
  -o "$APP/Contents/MacOS/corral" \
  "$SRC"/*.swift \
  -framework AppKit -framework SwiftUI -framework Combine \
  -framework UserNotifications

echo "▸ copying resources"
cp "$SRC/Info.plist"     "$APP/Contents/Info.plist"
cp "$SRC/corrald.py"     "$APP/Contents/Resources/corrald.py"
cp "$SRC/corral-tui.py"  "$APP/Contents/Resources/corral-tui.py"
[ -f "$SRC/AppIcon.icns" ] && cp "$SRC/AppIcon.icns" "$APP/Contents/Resources/AppIcon.icns"
[ -f "$SRC/AppIcon.svg" ]  && cp "$SRC/AppIcon.svg"  "$APP/Contents/Resources/AppIcon.svg"
if [ -d "$HERE/assets/horses" ]; then
  mkdir -p "$APP/Contents/Resources/horses"
  cp "$HERE"/assets/horses/*.svg "$APP/Contents/Resources/horses/"
fi
chmod +x "$APP/Contents/MacOS/corral"
chmod +x "$APP/Contents/Resources/corrald.py" "$APP/Contents/Resources/corral-tui.py"

echo "▸ ad-hoc code signing"
codesign --force --deep --sign - "$APP" 2>/dev/null || echo "  (codesign skipped)"

# Refresh LaunchServices / icon cache so Finder picks up changes immediately.
touch "$APP"

echo "✓ built: $APP"
