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
# Note the app is only ad-hoc signed (build.sh) — notarizing needs a paid Apple
# Developer account. That's why the *recommended* install path is the curl
# one-liner in site/install.sh: curl-downloaded files carry no quarantine flag,
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

Installs Tower to /Applications and launches it. No Gatekeeper warning — a
curl-downloaded app isn't quarantined.

Prefer to download by hand? Grab \`Tower.app.zip\` below (not \"Source code\" —
that has no built app in it). macOS will call it *unidentified* because the build
isn't notarized; clear that with:

\`\`\`sh
xattr -rd com.apple.quarantine /Applications/Tower.app
\`\`\`

Requires macOS 14+ on Apple Silicon, Python 3.8+, and Claude Code."
fi

echo "✓ published: $(gh release view "$TAG" --json url -q .url)"
