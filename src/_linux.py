#!/usr/bin/env python3
"""
_linux.py — the Linux edges of towerd, in one place.

Imported only when `sys.platform` starts with "linux" (see IS_LINUX in
towerd.py). It exists for the same reason _win.py does: the daemon is
otherwise portable stdlib, and only a handful of touch points are per-OS.

Linux differs from macOS in four places:

  * keep-awake       — no `caffeinate`/`pmset`; logind's `systemd-inhibit`
                       does the whole job, including the lid (so the macOS
                       sudoers/admin dance has no analog here at all).
  * a process's cwd  — /proc/<pid>/cwd is a symlink, so no `lsof`.
  * proxy clients    — /proc/net/tcp{,6} + /proc/<pid>/fd, so no `lsof`.
  * focusing a tab   — no osascript/Terminal.app; tmux only (handled in
                       towerd.py, which already has a tmux branch).

Everything here is stdlib and never raises: each helper answers with a
degraded-but-honest value (None / empty set / False) if /proc or logind is
not what we expect, because a monitor that crashes is worse than one that
reports "unknown".
"""

import os
import shutil

# logind inhibitor locks. "idle" keeps the session from going idle-to-sleep;
# "sleep" blocks a suspend request outright; "handle-lid-switch" is the piece
# macOS needs an admin password (pmset disablesleep + sudoers) to get — on
# Linux any user may take it, so Tower's "clamshell" mode is free here.
INHIBIT_IDLE = "idle:sleep"
INHIBIT_CLAMSHELL = "idle:sleep:handle-lid-switch"


def keepawake_argv(mode):
    """argv for a keep-awake holder process, or None if logind isn't available.

    `systemd-inhibit` holds the lock for as long as the command it runs lives,
    so we park it on `sleep infinity` and kill the process to release — the
    same lifecycle towerd already uses for `caffeinate`, so the caller's
    Popen/terminate code is unchanged."""
    inhibit = shutil.which("systemd-inhibit")
    if not inhibit:
        return None
    sleep = shutil.which("sleep") or "/bin/sleep"
    what = INHIBIT_CLAMSHELL if mode == "clamshell" else INHIBIT_IDLE
    return [inhibit, f"--what={what}", "--who=Tower",
            "--why=Claude agents are working", "--mode=block",
            sleep, "infinity"]


def has_logind_inhibit():
    return shutil.which("systemd-inhibit") is not None


def proc_cwd(pid):
    """The process's working directory, or None.

    /proc/<pid>/cwd is a symlink the kernel resolves for us — one readlink,
    no subprocess, and it only succeeds for processes we own (a PermissionError
    from another user's process is an expected None, not an error)."""
    try:
        return os.readlink(f"/proc/{pid}/cwd")
    except OSError:
        return None


def _hexip_is_loopback(h):
    """/proc/net/tcp writes the address as little-endian hex. 127.0.0.1 is
    "0100007F" in tcp, and "::1" / v4-mapped 127.0.0.1 in tcp6."""
    h = h.upper()
    if len(h) == 8:
        return h == "0100007F"
    if len(h) == 32:
        # "::1", and ::ffff:127.0.0.1 (v4-mapped, how a v6 socket sees it).
        return h.endswith("01000000") or h.endswith("0100007F")
    return False


def _established_to_port(port):
    """Socket inodes of ESTABLISHED connections whose *remote* end is
    127.0.0.1:<port> — i.e. clients of our proxy. State "01" is TCP_ESTABLISHED.
    The daemon's own accept-side sockets have the port on the *local* side and
    are naturally excluded."""
    want = f"{port:04X}"
    inodes = set()
    for name in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            with open(name) as f:
                next(f, None)                      # header
                for line in f:
                    parts = line.split()
                    if len(parts) < 10 or parts[3] != "01":
                        continue
                    rem_ip, _, rem_port = parts[2].partition(":")
                    if rem_port.upper() != want:
                        continue
                    if not _hexip_is_loopback(rem_ip):
                        continue
                    try:
                        inodes.add(int(parts[9]))
                    except ValueError:
                        pass
        except OSError:
            continue
    return inodes


def proxy_client_pids(port):
    """PIDs holding a live connection to the proxy — the /proc answer to the
    `lsof -iTCP@127.0.0.1:<port> -sTCP:ESTABLISHED` macOS uses.

    Two passes: read the socket inodes out of /proc/net/tcp{,6}, then find who
    holds them by reading /proc/<pid>/fd. The second pass is skipped entirely
    when there are no connections, which is the common case."""
    inodes = _established_to_port(port)
    if not inodes:
        return set()
    targets = {f"socket:[{i}]" for i in inodes}
    pids = set()
    try:
        entries = os.listdir("/proc")
    except OSError:
        return pids
    for e in entries:
        if not e.isdigit():
            continue
        fddir = f"/proc/{e}/fd"
        try:
            fds = os.listdir(fddir)
        except OSError:
            continue                # not ours, or exited mid-scan
        for fd in fds:
            try:
                if os.readlink(os.path.join(fddir, fd)) in targets:
                    pids.add(int(e))
                    break
            except OSError:
                continue
    return pids
