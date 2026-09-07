#!/bin/bash
#
# ci-smoke.sh — install the built .deb on this system and prove it works.
#
# Meant to run inside a throwaway Ubuntu container (it installs packages and
# writes to $HOME), one per release we claim to support:
#
#   docker run --rm -v "$PWD:/pkg" -w /pkg ubuntu:22.04 \
#     bash packaging/deb/ci-smoke.sh dist/tower_3.2.0_all.deb
#
# What it actually checks — the packaging claims, not the app's features:
#   * apt can resolve the declared Depends on this Ubuntu (so `apt install`,
#     never `dpkg -i`, which would skip exactly that half),
#   * the daemon starts on this Ubuntu's Python and writes state,
#   * it reports platform "linux" and brings its proxy up,
#   * it installs routing into ~/.claude/settings.json,
#   * SIGTERM takes that routing back out — the invariant that a stopped Tower
#     leaves Claude Code on a working direct connection,
#   * removing the package removes the files.
#
# And for the top-bar radar, both halves of the Recommends bargain:
#   * installed WITHOUT recommends (the headless case), `tower-tray` exits 1
#     naming the packages it wants — never a traceback,
#   * with those packages added, apt can resolve them on this Ubuntu and the GI
#     typelibs really import, and `tower-tray` then exits 1 for the honest
#     reason: a container has no session to put a top bar in.
set -euo pipefail

DEB="${1:?usage: ci-smoke.sh <path-to-.deb>}"
HERE="$(cd "$(dirname "$0")" && pwd)"
export DEBIAN_FRONTEND=noninteractive

step() { printf '\n▸ %s\n' "$*"; }

step "installing $DEB (without recommends — the headless case)"
apt-get update -qq
# `apt install ./file.deb` (not dpkg -i) so Depends are resolved for real.
# --no-install-recommends is the point of this first pass: it proves the daemon
# and the dashboard stand on python3 + procps alone.
apt-get install -y -qq --no-install-recommends "./$DEB" >/dev/null
command -v tower
command -v towerd
command -v tower-tray
test -f /usr/lib/systemd/user/tower.service
test -f /usr/lib/systemd/user/tower-tray.service
# Ask dpkg, not the filesystem: the official Ubuntu container images ship a
# dpkg exclude for /usr/share/man, so an installed man page is legitimately
# absent there while still being in the package.
dpkg -L tower | grep -q 'man1/tower\.1\.gz'
dpkg -L tower | grep -q 'man1/tower-tray\.1\.gz'

step "python version on this release"
python3 -V
# The build machine byte-compiles with its own (newer) Python; this is the one
# that matters — 22.04 ships 3.10, so a newer-syntax slip has to fail here.
python3 -m py_compile /usr/lib/tower/towerd.py \
                      /usr/lib/tower/tower-tui.py \
                      /usr/lib/tower/tower-tray.py \
                      /usr/lib/tower/_linux.py
echo "  byte-compiles"

step "the daemon comes up and guards"
export HOME=/tmp/towerhome
rm -rf "$HOME"
mkdir -p "$HOME/.claude"
echo '{}' > "$HOME/.claude/settings.json"
TOWER_PORT=18888 towerd &
pid=$!

for _ in $(seq 1 40); do
  [ -f "$HOME/.tower/state.json" ] && break
  sleep 1
done
test -f "$HOME/.tower/state.json" || { echo "no state.json"; exit 1; }

python3 "$HERE/ci-assert.py"

grep -q HTTPS_PROXY "$HOME/.claude/settings.json" \
  || { echo "routing was not installed"; cat "$HOME/.claude/settings.json"; exit 1; }
echo "  routing installed"

step "SIGTERM un-routes"
kill -TERM "$pid"
for _ in $(seq 1 25); do
  grep -q HTTPS_PROXY "$HOME/.claude/settings.json" || break
  sleep 1
done
if grep -q HTTPS_PROXY "$HOME/.claude/settings.json"; then
  echo "FAIL: settings.json still routed after SIGTERM"
  cat "$HOME/.claude/settings.json"
  exit 1
fi
echo "  un-routed"
cat "$HOME/.tower/daemon.log"

# One helper for both passes: run the tray, demand exit 1, and demand that what
# it printed contains the phrase a person needs to read.
expect_tray_says() {
  set +e
  out=$(tower-tray 2>&1); rc=$?
  set -e
  [ "$rc" = "1" ] || { echo "FAIL: expected exit 1, got $rc"; echo "$out"; exit 1; }
  case "$out" in
    *"$1"*) printf '  %s\n' "$out" | head -3 ;;
    *) echo "FAIL: expected to see '$1', got:"; echo "$out"; exit 1 ;;
  esac
}

step "without the toolkit, the tray names what it needs"
expect_tray_says "no AppIndicator support found"

step "adding the recommended toolkit"
# The other half: these are the Recommends, and apt has to be able to resolve
# them on this release for the top bar to work at all.
apt-get install -y -qq --no-install-recommends \
  python3-gi python3-gi-cairo gir1.2-gtk-3.0 \
  gir1.2-ayatanaappindicator3-0.1 >/dev/null
python3 - <<'PYCHECK'
# A satisfied dependency line is not proof: the typelibs have to load.
import gi
gi.require_version("Gtk", "3.0")
for name in ("AyatanaAppIndicator3", "AppIndicator3"):
    try:
        gi.require_version(name, "0.1")
        __import__("gi.repository." + name)
        print("  indicator bindings:", name)
        break
    except (ValueError, ImportError):
        continue
else:
    raise SystemExit("no AppIndicator typelib after installing the toolkit")
from gi.repository import Gtk          # noqa: F401
import cairo                            # noqa: F401  (python3-gi-cairo)
print("  gtk3 + cairo import clean")
PYCHECK

step "with the toolkit but no session, it says that instead"
expect_tray_says "no graphical session"

step "removal"
apt-get remove -y -qq tower >/dev/null
test ! -e /usr/bin/tower-tray
test ! -e /usr/lib/tower/towerd.py
test ! -e /usr/bin/tower

printf '\n✓ %s is good on %s\n' "$DEB" "$(. /etc/os-release && echo "$PRETTY_NAME")"
