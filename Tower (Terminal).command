#!/bin/bash
# Double-click to open the Tower terminal dashboard (TUI).
# Same guard, same live data as the menubar app — just in your terminal.
#
# If you installed Tower (curl -fsSL .../install.sh | sh) you don't need this
# file at all — just type `tower`. This is the source-checkout convenience.
HERE="$(cd "$(dirname "$0")" && pwd)"

# The shim knows how to find the TUI from anywhere; prefer it when it's built.
for launcher in \
  "$HERE/Tower.app/Contents/Resources/tower" \
  "$HERE/src/tower"
do
  [ -x "$launcher" ] && exec "$launcher"
done

# No shim (older checkout) — fall back to running the TUI directly.
TUI="$HERE/Tower.app/Contents/Resources/tower-tui.py"
[ -f "$TUI" ] || TUI="$HERE/src/tower-tui.py"
exec python3 "$TUI"
