#!/bin/bash
#
# build.sh — build the Tower .deb for Ubuntu 22.04 through 26.04.
#
#   packaging/deb/build.sh                 # → dist/tower_<version>_all.deb
#   packaging/deb/build.sh --version 3.1.1 # override the version
#   packaging/deb/build.sh --install       # build, then `sudo apt install` it
#
# One package with everything: the daemon, the terminal dashboard, and the
# top-bar radar. GTK sits in Recommends rather than Depends, so the same .deb
# still installs on a headless machine with
# `apt install --no-install-recommends` — you get the daemon and the dashboard,
# and `tower-tray` tells you which packages the top bar wants. On a desktop,
# apt pulls them by default and the radar just works.
#
# Architecture: all — Tower on Linux compiles nothing (the Swift menu-bar app
# is macOS-only and is not in the package), so one build covers amd64 and arm64.
#
# Deliberately built with plain `dpkg-deb --build --root-owner-group`, not
# debhelper: nothing here needs compiling, so the only build dependency is dpkg
# itself — the same script runs on 22.04 and on 26.04, and in a CI container
# with no build-essential.
#
# The version comes from src/Info.plist (CFBundleShortVersionString), the same
# single source release.sh uses, so the .deb and the macOS app can never
# disagree about what version they are.
set -euo pipefail

# The build must not inherit the caller's umask: on Ubuntu it is 002, which
# would ship group-writable directories and man pages (and dpkg-deb only
# rewrites ownership, not modes).
umask 022

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
DIST="$ROOT/dist"
MAINTAINER="${DEB_MAINTAINER:-Tower contributors <noreply@github.com>}"

VERSION=""
DO_INSTALL=0
while [ $# -gt 0 ]; do
  case "$1" in
    --version) VERSION="${2:?--version needs a value}"; shift 2 ;;
    --install) DO_INSTALL=1; shift ;;
    -h|--help) sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "build.sh: unknown argument '$1'" >&2; exit 1 ;;
  esac
done

command -v dpkg-deb >/dev/null 2>&1 || {
  echo "error: dpkg-deb not found — this script builds a Debian package." >&2
  exit 1
}
command -v python3 >/dev/null 2>&1 || {
  echo "error: python3 not found (needed to read src/Info.plist)." >&2
  exit 1
}

if [ -z "$VERSION" ]; then
  VERSION="$(python3 - "$ROOT/src/Info.plist" <<'PY'
import plistlib, sys
with open(sys.argv[1], "rb") as f:
    print(plistlib.load(f)["CFBundleShortVersionString"])
PY
)"
fi

# Debian versions are ordered, and an X.Y that sorts next to an existing X.Y.Z
# is the same trap release.sh guards against for tags.
case "$VERSION" in
  [0-9]*.[0-9]*.[0-9]*) : ;;
  *) echo "error: version '$VERSION' must be X.Y.Z." >&2; exit 1 ;;
esac

PKG="$ROOT/build/deb/tower_${VERSION}_all"
DEB="$DIST/tower_${VERSION}_all.deb"

echo "▸ building tower $VERSION"

rm -rf "$PKG"
mkdir -p "$PKG/DEBIAN" \
         "$PKG/usr/lib/tower" \
         "$PKG/usr/bin" \
         "$PKG/usr/lib/systemd/user" \
         "$PKG/usr/share/applications" \
         "$PKG/usr/share/icons/hicolor/scalable/apps" \
         "$PKG/usr/share/man/man1" \
         "$PKG/usr/share/doc/tower"

# --- payload -------------------------------------------------------------- #
# The daemon, both front-ends, and the Linux platform shim. _win.py and
# _wincurses.py are left out on purpose: they are imported only when
# os.name == "nt", so on a Debian system they are dead weight.
install -m 0644 "$ROOT/src/towerd.py"      "$PKG/usr/lib/tower/towerd.py"
install -m 0644 "$ROOT/src/tower-tui.py"   "$PKG/usr/lib/tower/tower-tui.py"
install -m 0644 "$ROOT/src/tower-tray.py"  "$PKG/usr/lib/tower/tower-tray.py"
install -m 0644 "$ROOT/src/_linux.py"      "$PKG/usr/lib/tower/_linux.py"

install -m 0755 "$HERE/bin/tower"      "$PKG/usr/bin/tower"
install -m 0755 "$HERE/bin/tower-tray" "$PKG/usr/bin/tower-tray"
install -m 0755 "$HERE/bin/towerd"     "$PKG/usr/bin/towerd"

install -m 0644 "$HERE/tower.service" \
  "$PKG/usr/lib/systemd/user/tower.service"
install -m 0644 "$HERE/tower-tray.service" \
  "$PKG/usr/lib/systemd/user/tower-tray.service"
install -m 0644 "$HERE/tower.desktop" \
  "$PKG/usr/share/applications/tower.desktop"
install -m 0644 "$HERE/tower-tray.desktop" \
  "$PKG/usr/share/applications/tower-tray.desktop"
install -m 0644 "$HERE/tower.svg" \
  "$PKG/usr/share/icons/hicolor/scalable/apps/tower.svg"

# --- docs ----------------------------------------------------------------- #
install -m 0644 "$HERE/copyright" "$PKG/usr/share/doc/tower/copyright"
install -m 0644 "$ROOT/README.md" "$PKG/usr/share/doc/tower/README.md"
[ -f "$ROOT/docs/LINUX.md" ] && \
  install -m 0644 "$ROOT/docs/LINUX.md" "$PKG/usr/share/doc/tower/LINUX.md"

# gzip -n: no timestamp in the header, so two builds of the same source produce
# byte-identical files.
{
  printf 'tower (%s) unstable; urgency=medium\n\n' "$VERSION"
  printf '  * Tower %s for Debian/Ubuntu: daemon, terminal dashboard,\n' "$VERSION"
  printf '    and the top-bar radar.\n'
  printf '    Release notes: https://github.com/imanimen/tower/releases\n\n'
  printf ' -- %s  %s\n' "$MAINTAINER" "$(date -R)"
} > "$PKG/usr/share/doc/tower/changelog.Debian"
gzip -9n "$PKG/usr/share/doc/tower/changelog.Debian"
chmod 0644 "$PKG/usr/share/doc/tower/changelog.Debian.gz"

for m in tower tower-tray towerd; do
  sed "s/@VERSION@/$VERSION/g" "$HERE/$m.1" > "$PKG/usr/share/man/man1/$m.1"
  gzip -9n "$PKG/usr/share/man/man1/$m.1"
  chmod 0644 "$PKG/usr/share/man/man1/$m.1.gz"
done

# --- control ------------------------------------------------------------- #
SIZE="$(du -sk --apparent-size "$PKG" | cut -f1)"
sed -e "s/@VERSION@/$VERSION/g" \
    -e "s|@MAINTAINER@|$MAINTAINER|g" \
    -e "s/@SIZE@/$SIZE/g" \
    "$HERE/control.in" > "$PKG/DEBIAN/control"

install -m 0755 "$HERE/postinst" "$PKG/DEBIAN/postinst"
install -m 0755 "$HERE/prerm"    "$PKG/DEBIAN/prerm"
install -m 0755 "$HERE/postrm"   "$PKG/DEBIAN/postrm"

# md5sums, which dpkg-deb does not generate for us. Paths are relative to /.
( cd "$PKG" && find . -type f ! -path './DEBIAN/*' -printf '%P\0' \
  | sort -z | xargs -0 md5sum > DEBIAN/md5sums )

# --- byte-compile check --------------------------------------------------- #
# Fail the build rather than ship a syntax error: 22.04 runs Python 3.10, so a
# newer-syntax slip has to be caught here, not by a user.
python3 -m py_compile "$PKG/usr/lib/tower/towerd.py" \
                      "$PKG/usr/lib/tower/tower-tui.py" \
                      "$PKG/usr/lib/tower/tower-tray.py" \
                      "$PKG/usr/lib/tower/_linux.py"
find "$PKG" -name '__pycache__' -type d -exec rm -rf {} +

# --- build ---------------------------------------------------------------- #
mkdir -p "$DIST"
rm -f "$DEB"
# --root-owner-group: every file lands as root:root without needing fakeroot.
dpkg-deb --build --root-owner-group "$PKG" "$DEB" >/dev/null

echo "✓ $DEB"
dpkg-deb --info "$DEB" | sed -n '/^ Package:/,/^ Description:/p'

if command -v lintian >/dev/null 2>&1; then
  echo "▸ lintian (advisory)"
  lintian --no-tag-display-limit "$DEB" || true
fi

if [ "$DO_INSTALL" = "1" ]; then
  echo "▸ installing"
  sudo apt install -y "$DEB"
fi
