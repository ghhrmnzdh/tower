#!/bin/bash
#
# release.sh — build Tower.app, package it, and publish it to GitHub Releases.
#
#   ./release.sh              # publish (or update) the release for this version
#   ./release.sh --draft      # same, but leave the release as a draft
#
# The version comes from src/Info.plist (CFBundleShortVersionString), so bumping
# a release means bumping the plist — there is no second place to forget.
#
# Packaging uses `ditto -c -k --keepParent`, NOT `zip`: ditto preserves the
# bundle's execute bits and metadata. A zip made another way can land on a user's
# Mac as an app that won't launch.
#
# Note the app is only ad-hoc signed (build.sh), not notarized. That's why the
# *recommended* install path is the curl one-liner in site/install.sh:
# curl-downloaded files carry no quarantine flag,
# so Gatekeeper never shows the "unidentified developer" block. This zip stays
# published for people who'd rather download by hand (they get the Gatekeeper
# prompt, and the README tells them how to clear it).
#
# Requires: gh (authenticated — `gh auth login`).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
APP="$HERE/Tower.app"
ZIP="$HERE/Tower.app.zip"

DRAFT=""
[ "${1:-}" = "--draft" ] && DRAFT="--draft"

command -v gh >/dev/null 2>&1 || { echo "error: gh not found — https://cli.github.com" >&2; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "error: gh is not authenticated — run: gh auth login" >&2; exit 1; }

VERSION="$(plutil -extract CFBundleShortVersionString raw -o - "$HERE/src/Info.plist")"
[ -n "$VERSION" ] || { echo "error: no CFBundleShortVersionString in src/Info.plist" >&2; exit 1; }

# Tags are vX.Y.Z. Insist on three parts, or a plist reading "3.0" would tag
# v3.0 *alongside* the existing v3.0.0 — two tags for one version, and a
# /releases/latest that points at whichever GitHub decides is newest.
case "$VERSION" in
  [0-9]*.[0-9]*.[0-9]*) : ;;
  *) echo "error: CFBundleShortVersionString is '$VERSION' — must be X.Y.Z to match the vX.Y.Z tags." >&2; exit 1 ;;
esac
TAG="v$VERSION"

echo "▸ releasing $TAG"

"$HERE/build.sh"

echo "▸ packaging $ZIP"
rm -f "$ZIP"
ditto -c -k --keepParent "$APP" "$ZIP"

if gh release view "$TAG" >/dev/null 2>&1; then
  echo "▸ $TAG exists — replacing its asset"
  gh release upload "$TAG" "$ZIP" --clobber
else
  echo "▸ creating $TAG"
  gh release create "$TAG" "$ZIP" \
    $DRAFT \
    --title "Tower $VERSION" \
    --notes "## Install

\`\`\`sh
curl -fsSL https://ghhrmnzdh.github.io/tower/install.sh | sh
\`\`\`

Installs Tower to /Applications, puts the \`tower\` command on your PATH, and
launches it. **No Gatekeeper warning** — a curl-downloaded file is never
quarantined, so macOS doesn't assess it.

Menu bar: the radar appears at the top right.
Terminal dashboard: type \`tower\`, or click **Terminal Dashboard…** in the popover.

### Downloading by hand instead?

Grab \`Tower.app.zip\` below — *not* \"Source code\", which contains no built app.
macOS quarantines browser downloads, and because this build isn't notarized it
will refuse to open it as *\"from an unidentified developer.\"* On macOS 15+,
right-click → Open no longer clears this. Either:

\`\`\`sh
xattr -rd com.apple.quarantine /Applications/Tower.app
\`\`\`

…or open it once and choose **Open Anyway** in System Settings → Privacy &
Security. The one-liner above avoids all of it.

Requires macOS 14+ on Apple Silicon, Python 3, and Claude Code."
fi

echo "✓ published: $(gh release view "$TAG" --json url -q .url)"
