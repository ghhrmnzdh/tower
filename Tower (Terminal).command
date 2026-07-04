#!/bin/bash
# Double-click to open the Tower terminal dashboard (TUI).
# Same guard, same live data as the menubar app — just in your terminal.
HERE="$(cd "$(dirname "$0")" && pwd)"
TUI="$HERE/Tower.app/Contents/Resources/tower-tui.py"
[ -f "$TUI" ] || TUI="$HERE/src/tower-tui.py"
exec python3 "$TUI"
