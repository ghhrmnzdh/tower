#!/bin/sh
#
# install.sh — one-line installer for Tower.
#
#   curl -fsSL https://ghhrmnzdh.github.io/tower/install.sh | sh
#
# Why this exists: files fetched with curl are NOT flagged with
# com.apple.quarantine, so Gatekeeper never assesses them. A browser download of
# the same zip *is* flagged, and because Tower is only ad-hoc signed (not
# notarized — that needs a paid Apple Developer account), Gatekeeper blocks it
# with "unidentified developer". Installing via curl sidesteps that entirely:
# the app just opens.
#
# Everything lives inside main(), called on the last line, so a half-downloaded
# script executes nothing. No sudo, no interactive prompts (stdin is the pipe).
set -eu

REPO="ghhrmnzdh/tower"
ASSET="Tower.app.zip"
URL="https://github.com/$REPO/releases/latest/download/$ASSET"

# Colors only when stdout is a terminal (it is, even when stdin is the pipe).
if [ -t 1 ]; then
  B=$(printf '\033[1m'); DIM=$(printf '\033[2m'); G=$(printf '\033[32m')
  R=$(printf '\033[31m'); Z=$(printf '\033[0m')
else
  B=''; DIM=''; G=''; R=''; Z=''
fi

say()  { printf '%s\n' "$*"; }
step() { printf '%s▸%s %s\n' "$DIM" "$Z" "$*"; }
die()  { printf '%serror:%s %s\n' "$R" "$Z" "$*" >&2; exit 1; }

TMP=""
cleanup() { [ -n "$TMP" ] && rm -rf "$TMP"; }

preflight() {
  [ "$(uname -s)" = "Darwin" ] || die "Tower's app is macOS-only. (Windows/Linux: the terminal dashboard runs from source — see https://github.com/$REPO)"

  [ "$(uname -m)" = "arm64" ] || die "Tower.app is built for Apple Silicon (arm64) and this Mac is $(uname -m).
       Build it from source instead: git clone https://github.com/$REPO && cd tower && ./build.sh"

  major=$(sw_vers -productVersion 2>/dev/null | cut -d. -f1)
  case "$major" in
    ''|*[!0-9]*) : ;;   # unreadable version — don't block on a guess
    *) [ "$major" -ge 14 ] || die "Tower needs macOS 14 or later (this Mac is $(sw_vers -productVersion))." ;;
  esac

  command -v curl   >/dev/null 2>&1 || die "curl not found."
  command -v ditto  >/dev/null 2>&1 || die "ditto not found."
}

# Where the app goes: /Applications when we can write it without sudo (true for
# admin accounts), otherwise the per-user ~/Applications.
choose_dest() {
  if [ -w /Applications ]; then
    printf '/Applications'
  else
    mkdir -p "$HOME/Applications"
    printf '%s/Applications' "$HOME"
  fi
}

# Put the `tower` command on PATH, so the terminal dashboard is one word instead
# of `python3 "/Applications/Tower.app/Contents/Resources/tower-tui.py"`.
# Prefer a bin dir that is BOTH writable without sudo and already on PATH; fall
# back to ~/.local/bin and tell the user how to reach it. Never sudo.
link_cli() {
  shim="$1/Tower.app/Contents/Resources/tower"
  [ -f "$shim" ] || return 0

  bindir=''
  for d in /opt/homebrew/bin /usr/local/bin "$HOME/.local/bin" "$HOME/bin"; do
    if [ -d "$d" ] && [ -w "$d" ] && case ":$PATH:" in *":$d:"*) true ;; *) false ;; esac; then
      bindir=$d; break
    fi
  done

  if [ -z "$bindir" ]; then
    bindir="$HOME/.local/bin"
    mkdir -p "$bindir" || return 0
  fi

  ln -sf "$shim" "$bindir/tower" 2>/dev/null || return 0
  step "linked the 'tower' command into $bindir"

  # Symlinked somewhere off-PATH — say so rather than leave a command that
  # silently doesn't exist.
  case ":$PATH:" in
    *":$bindir:"*) CLI_READY=1 ;;
    *) CLI_HINT="$bindir" ;;
  esac
}

main() {
  printf '\n  %sTower%s — control tower for your Claude agents\n\n' "$B" "$Z"

  preflight

  trap cleanup EXIT INT TERM
  TMP=$(mktemp -d)

  step "downloading the latest release"
  curl -fL --progress-bar -o "$TMP/$ASSET" "$URL" \
    || die "download failed. Check your connection, or grab $ASSET by hand: https://github.com/$REPO/releases/latest"

  step "unpacking"
  # ditto (not unzip): preserves the bundle's execute bits and structure.
  ditto -x -k "$TMP/$ASSET" "$TMP/unpacked" || die "could not unpack $ASSET."
  [ -d "$TMP/unpacked/Tower.app" ] || die "the release archive has no Tower.app inside it."

  # Quit a running copy first. A clean quit un-routes Claude Code (removes the
  # proxy from ~/.claude/settings.json); the new copy re-arms it at launch.
  if pgrep -x Tower >/dev/null 2>&1; then
    step "quitting the running Tower"
    osascript -e 'tell application "Tower" to quit' >/dev/null 2>&1 || true
    n=0
    while pgrep -x Tower >/dev/null 2>&1 && [ "$n" -lt 20 ]; do
      sleep 0.25
      n=$((n + 1))
    done
  fi

  DEST=$(choose_dest)
  step "installing to $DEST/Tower.app"
  rm -rf "$DEST/Tower.app" || die "could not replace $DEST/Tower.app — is it still running?"
  mv "$TMP/unpacked/Tower.app" "$DEST/Tower.app" || die "could not move Tower.app into $DEST."

  # A curl download carries no quarantine flag, so this is a no-op here — it's
  # here so the script also rescues a copy someone already downloaded by browser.
  xattr -rd com.apple.quarantine "$DEST/Tower.app" >/dev/null 2>&1 || true

  link_cli "$DEST"

  step "starting Tower"
  open "$DEST/Tower.app" || die "installed, but could not launch it. Open $DEST/Tower.app yourself."

  printf '\n  %s✓%s Tower is running — look for the radar in your menu bar.\n\n' "$G" "$Z"
  if [ -n "${CLI_READY:-}" ]; then
    printf '    Terminal dashboard:  %stower%s\n\n' "$B" "$Z"
  elif [ -n "${CLI_HINT:-}" ]; then
    printf '    Terminal dashboard:  %stower%s — add its folder to your PATH first:\n' "$B" "$Z"
    printf '      %secho '\''export PATH="%s:$PATH"'\'' >> ~/.zshrc && exec zsh%s\n\n' "$DIM" "$CLI_HINT" "$Z"
  fi
}

main "$@"
