#!/bin/bash
# Opens the Tower terminal dashboard in Terminal.
#
# This lives inside the app bundle (Contents/Resources). It exists because
# Terminal reliably opens and runs a *.command file — that's what the popover's
# "Terminal Dashboard…" item hands to LaunchServices, which costs no automation
# permission prompt (an AppleScript "tell Terminal" would). All it does is run
# the `tower` shim sitting next to it.
HERE="$(cd "$(dirname "$0")" && pwd)"
exec "$HERE/tower"
