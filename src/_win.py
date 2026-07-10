"""
_win — Windows-only platform shim for towerd.

Imported by towerd.py *only* when os.name == "nt". Every function here is the
Windows equivalent of a Unix touch point that has no cross-platform stdlib
counterpart:

  * single_instance()        <- fcntl.flock daemon lock  (named mutex)
  * keepawake(on)            <- caffeinate / pmset        (SetThreadExecutionState)
  * enum_claude_processes()  <- ps -axo ...               (CIM / Win32_Process)
  * enable_vt_and_utf8()     <- (n/a on macOS)            (console VT + UTF-8)

Pure stdlib: ctypes + subprocess only. Keeps towerd.py free of ctypes noise and
lets the daemon stay one otherwise-portable file.
"""

import ctypes
import json
import subprocess
import sys
from ctypes import wintypes

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)

ERROR_ALREADY_EXISTS = 183

# Keep-alive handle for the single-instance mutex. Stored at module scope so it
# is never garbage-collected (which would release the mutex) for the life of the
# process; the daemon also stashes it on `state`, but this is belt-and-braces.
_mutex_handle = None


# --------------------------------------------------------------------------- #
# Single instance — named mutex (replaces fcntl.flock on ~/.tower/daemon.lock)
# --------------------------------------------------------------------------- #
def single_instance(name="Local\\TowerDaemon"):
    """Return an opaque handle if we are the first/only instance, or None if a
    daemon is already running. The handle must be kept referenced for the life
    of the process; closing/GC-ing it releases the lock.

    Named in the per-session `Local\\` namespace (not `Global\\`): the daemon is
    per-user, like the fcntl lock it replaces. `Global\\` both collides across
    users (a second user's daemon would refuse to start) and needs
    SeCreateGlobalPrivilege — whose absence for a normal account is exactly what
    used to send us down the fail-open path below."""
    global _mutex_handle
    _k32.CreateMutexW.restype = wintypes.HANDLE
    _k32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    _k32.CloseHandle.restype = wintypes.BOOL
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = _k32.CreateMutexW(None, False, name)
    err = ctypes.get_last_error()
    if not handle:
        # Couldn't create the mutex at all (OOM / handle exhaustion). Fail
        # CLOSED — never launch a second router when we can't prove we're alone.
        return None
    if err == ERROR_ALREADY_EXISTS:
        _k32.CloseHandle(handle)
        return None
    _mutex_handle = handle
    return handle


# --------------------------------------------------------------------------- #
# Keep-awake — SetThreadExecutionState (replaces caffeinate / pmset / sudoers)
# --------------------------------------------------------------------------- #
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002


def keepawake(on):
    """Keep the machine (and display) awake while `on`. No admin, no clamshell
    concept — the Windows analog of `caffeinate -dimsu`. Returns True on success.
    The continuous state persists for the life of this process; releasing is
    just the ES_CONTINUOUS-only call."""
    _k32.SetThreadExecutionState.restype = wintypes.DWORD
    _k32.SetThreadExecutionState.argtypes = [wintypes.DWORD]
    if on:
        flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
    else:
        flags = ES_CONTINUOUS
    return _k32.SetThreadExecutionState(flags) != 0


# --------------------------------------------------------------------------- #
# Process enumeration — CIM / Win32_Process (replaces `ps -axo ...`)
# --------------------------------------------------------------------------- #
# We shell out to PowerShell's CIM provider because it is the only dependency-
# free way to read another process's *full command line* on Windows (the Win32
# toolhelp snapshot exposes the image name only, and reading the PEB directly is
# fragile). The command line is what carries --session-id / --resume, which the
# daemon needs to correlate a live process to its transcript. Throttled by the
# caller (PROC_RESCAN_S), so the PowerShell startup cost is paid rarely.
_PS_ENUM = (
    # Force UTF-8 out of PowerShell so non-ASCII command lines (accented user
    # dirs, unicode --resume titles) survive; paired with a utf-8 decode below.
    "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
    "$ErrorActionPreference='SilentlyContinue';"
    "Get-CimInstance Win32_Process -Filter \"Name='claude.exe' or Name='node.exe'\""
    " | ForEach-Object {"
    "  [pscustomobject]@{"
    "    pid=$_.ProcessId; ppid=$_.ParentProcessId; cmd=$_.CommandLine;"
    "    epoch=if($_.CreationDate){[int64]([datetimeoffset]$_.CreationDate)"
    ".ToUnixTimeSeconds()}else{$null}"
    "  }"
    "} | ConvertTo-Json -Compress"
)

CREATE_NO_WINDOW = 0x08000000


def enum_claude_processes():
    """Return a list of raw process rows for candidate Claude Code processes,
    shaped for towerd's ProcScanner.scan() shared parser:

        [{"pid": int, "ppid": int, "tty": None, "stopped": False,
          "lstart": float|None, "args": <full command line str>}]

    `node.exe` rows whose command line does not mention claude are filtered out
    here. Windows has no tty and no cheap SIGSTOP detection, so tty is always
    None and stopped always False."""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_ENUM],
            capture_output=True, encoding="utf-8-sig", errors="replace",
            timeout=15, creationflags=CREATE_NO_WINDOW)
    except Exception:
        return []
    out = (r.stdout or "").strip()
    if not out:
        return []
    try:
        data = json.loads(out)
    except Exception:
        return []
    if isinstance(data, dict):          # ConvertTo-Json emits a bare object for 1
        data = [data]
    rows = []
    for d in data:
        try:
            pid = int(d.get("pid"))
        except (TypeError, ValueError):
            continue
        cmd = d.get("cmd") or ""
        # node.exe that is not running the claude CLI is noise.
        if "claude" not in cmd.lower():
            continue
        ppid = d.get("ppid")
        try:
            ppid = int(ppid)
        except (TypeError, ValueError):
            ppid = 0
        epoch = d.get("epoch")
        lstart = float(epoch) if isinstance(epoch, (int, float)) else None
        rows.append({"pid": pid, "ppid": ppid, "tty": None,
                     "stopped": False, "lstart": lstart, "args": cmd})
    return rows


# --------------------------------------------------------------------------- #
# Console — enable ANSI VT sequences + UTF-8 (used by the TUI shim)
# --------------------------------------------------------------------------- #
ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
STD_OUTPUT_HANDLE = -11


def enable_vt_and_utf8():
    """Turn on VT/ANSI escape processing and switch the console to UTF-8 so the
    TUI's box-drawing and block glyphs render. Best-effort; safe to call twice."""
    # Prototype the console calls: without an explicit HANDLE restype ctypes
    # treats GetStdHandle's return as a 32-bit int and truncates the handle on
    # 64-bit Windows, so GetConsoleMode then fails and VT never turns on.
    _k32.GetStdHandle.restype = wintypes.HANDLE
    _k32.GetConsoleMode.restype = wintypes.BOOL
    _k32.GetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.LPDWORD]
    _k32.SetConsoleMode.restype = wintypes.BOOL
    _k32.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    try:
        h = _k32.GetStdHandle(STD_OUTPUT_HANDLE)
        mode = wintypes.DWORD()
        if _k32.GetConsoleMode(h, ctypes.byref(mode)):
            _k32.SetConsoleMode(
                h, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING)
    except Exception:
        pass
    try:
        _k32.SetConsoleOutputCP(65001)
        _k32.SetConsoleCP(65001)
    except Exception:
        pass
    # Make Python's stdout emit UTF-8 regardless of the console's legacy codepage.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
    except Exception:
        pass
