#!/bin/bash
# Double-click to open the Corral terminal dashboard (TUI).
# Same guard, same live data as the menubar app — just in your terminal.
HERE="$(cd "$(dirname "$0")" && pwd)"
TUI="$HERE/Corral.app/Contents/Resources/corral-tui.py"
[ -f "$TUI" ] || TUI="$HERE/src/corral-tui.py"
exec python3 "$TUI"
