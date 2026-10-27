#!/usr/bin/env python3
"""
_linux.py — the Linux edges of towerd, in one place.

Imported only when `sys.platform` starts with "linux" (see IS_LINUX in
towerd.py). It exists for the same reason _win.py does: the daemon is
otherwise portable stdlib, and only a handful of touch points are per-OS.

Linux differs from macOS in three places:

  * keep-awake       — no `caffeinate`/IOKit; logind's `systemd-inhibit` does
                       the whole job, including the lid, for any user.
  * a process's cwd  — /proc/<pid>/cwd is a symlink, so no `lsof`/libproc.
  * focusing a tab   — no osascript/Terminal.app; tmux only (handled in
                       towerd.py, which already has a tmux branch).

Everything here is stdlib and never raises: each helper answers with a
degraded-but-honest value (None) if /proc or logind is not
what we expect, because a monitor that crashes is worse than one that
reports "unknown".
"""

import os
import shutil

# logind inhibitor locks. "idle" keeps the session from going idle-to-sleep;
# "sleep" blocks a suspend request outright; "handle-lid-switch" keeps a closed
# lid from suspending — what macOS reaches through IOKit's clamshell call. Any
# user may take all three, so Tower's "clamshell" mode needs no admin here.
INHIBIT_IDLE = "idle:sleep"
INHIBIT_CLAMSHELL = "idle:sleep:handle-lid-switch"


def keepawake_argv(mode, owner_pid):
    """argv for a keep-awake holder process, or None if logind isn't available.

    `systemd-inhibit` holds the lock for as long as the command it runs lives.
    That command waits on the daemon's pid (`kill -0` every few seconds) rather
    than `sleep infinity`, so the lock dies with the daemon — even a kill -9 or
    an OOM kill — the same lifecycle `caffeinate -w <pid>` gives on macOS. The
    daemon still terminates it directly to release sooner."""
    inhibit = shutil.which("systemd-inhibit")
    if not inhibit:
        return None
    what = INHIBIT_CLAMSHELL if mode == "clamshell" else INHIBIT_IDLE
    watch = f"while kill -0 {int(owner_pid)} 2>/dev/null; do sleep 5; done"
    return [inhibit, f"--what={what}", "--who=Tower",
            "--why=Claude agents are working", "--mode=block",
            "/bin/sh", "-c", watch]


def proc_cwd(pid):
    """The process's working directory, or None.

    /proc/<pid>/cwd is a symlink the kernel resolves for us — one readlink,
    no subprocess, and it only succeeds for processes we own (a PermissionError
    from another user's process is an expected None, not an error)."""
    try:
        return os.readlink(f"/proc/{pid}/cwd")
    except OSError:
        return None
