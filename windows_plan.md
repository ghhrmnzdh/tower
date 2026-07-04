# Geo Guard on Windows — implementation plan

> Written before the macOS app was renamed to **Corral** (and grew network
> health + agent monitoring). Names and paths below (`geoguardd`,
> `~/.geo-guard`) map to `corrald` / `~/.corral` in the current codebase.

This document describes how to recreate the exact experience we built on macOS —
a **native tray app** plus a **terminal dashboard**, both driven by the same
Python daemon — on Windows 10/11.

The guiding principle is unchanged: **one daemon owns all logic and state; the
UIs are thin front-ends that read one JSON file and write command files.** That
split is what makes the port tractable — ~80% of the code (`geoguardd.py`) is
already portable Python; only the OS-specific edges and the native UI change.

---

## 1. Architecture parity

| Layer | macOS (this repo) | Windows equivalent |
|---|---|---|
| Core daemon | `geoguardd.py` (stdlib) | Same file, with a small `platform` shim (see §2) |
| State channel | `~/.geo-guard/state.json` | `%USERPROFILE%\.geo-guard\state.json` (identical) |
| Command channel | `~/.geo-guard/cmd/*.json` | Same (identical) |
| Native UI | Swift `NSStatusItem` menubar app | **C#/.NET `NotifyIcon` tray app** (WPF or WinUI 3) |
| Terminal UI | Python `curses` TUI | Python TUI using **ANSI + `msvcrt`** (stdlib) or `windows-curses` |
| Routing | writes `HTTPS_PROXY` into `~/.claude/settings.json` | **Identical** — Claude Code reads the same file on Windows |

The routing mechanism is the single most important thing that ports **for free**:
Claude Code honors `env.HTTPS_PROXY` / `env.HTTP_PROXY` in
`%USERPROFILE%\.claude\settings.json` on every platform. No Windows-specific
proxy plumbing is needed.

---

## 2. Porting `geoguardd.py` (the daemon)

Keep it as one file. Introduce a tiny platform layer for the four Unix-only
touch points:

### 2a. Single-instance lock — replace `fcntl.flock`
`fcntl` does not exist on Windows.
- **Option A (stdlib):** `msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)` on an opened
  lock file.
- **Option B (recommended):** a **named mutex** via `ctypes`:
  `kernel32.CreateMutexW(None, False, "Global\\GeoGuardDaemon")` and check
  `GetLastError() == ERROR_ALREADY_EXISTS`. Cleaner semantics than file locks.

Wrap it:
```python
if os.name == "nt":
    from _win import single_instance   # ctypes named mutex
else:
    # existing fcntl.flock path
```

### 2b. Signals — `SIGTERM`/`SIGINT`
`signal.SIGTERM` is limited on Windows. Use:
- `signal.SIGINT` (Ctrl-C) works.
- For clean shutdown from the tray app, rely on the existing **`{"cmd":"quit"}`
  command file** — the tray app already sends it. This is the primary shutdown
  path and is fully cross-platform. Keep the signal handlers guarded by
  `if hasattr(signal, "SIGTERM")`.

The critical safety invariant — **`route_off()` runs on shutdown** — must be
preserved. Since `quit` is delivered as a command (not a signal), the daemon's
main loop breaks and the existing `finally:` block runs `route_off()` unchanged.

### 2c. Keep-awake — replace `caffeinate` / `pmset`
No `caffeinate` on Windows. Use `SetThreadExecutionState` via `ctypes` (no admin
required, unlike the macOS clamshell path which needs sudoers):
```python
ES_CONTINUOUS       = 0x80000000
ES_SYSTEM_REQUIRED  = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002
kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED)
# release: SetThreadExecutionState(ES_CONTINUOUS)
```
The "lid closed / clamshell" mode has no Windows analog — drop it from the
Windows build and expose only `off` / `idle`. **No admin, no sudoers, no
`osascript`** — so `_osascript_admin`, `_install_clamshell_rule`,
`_remove_clamshell_rule`, and the `SUDOERS_FILE` logic are simply not compiled in
on Windows.

### 2d. Paths & atomic writes
- `os.path.expanduser("~")` → `%USERPROFILE%` automatically. ✅
- `os.replace()` (used by `_atomic_write`) is atomic on the same volume on
  Windows. ✅
- `tempfile.mkstemp(dir=...)` works. ✅

**Everything else** — the proxy (`socket`, `threading`), geolocation
(`urllib`), the transcript usage index, the state writer, and the command
watcher — is pure stdlib and runs unmodified.

Deliverable: `geoguardd.py` + `_win.py` (ctypes helpers, imported only when
`os.name == "nt"`).

---

## 3. Native tray app (the menubar analog)

Build in **C# / .NET 8** — it is to Windows what Swift/AppKit is to macOS:
first-party, no runtime to bundle if published self-contained, and gives a real
`NotifyIcon` in the system tray.

### Recommended stack
- **WinUI 3** (or WPF if targeting older machines) for the flyout window.
- `System.Windows.Forms.NotifyIcon` (usable from WPF/WinUI) for the tray icon +
  context menu. It is the closest match to `NSStatusItem`.

### Behavior (mirror `menubar.swift` 1:1)
1. **On launch:** locate and start the daemon if `state.json` is stale.
   ```
   Process.Start("python", "geoguardd.py")   // or a bundled python
   ```
   The daemon's single-instance lock makes a redundant launch harmless.
2. **Poll** `%USERPROFILE%\.geo-guard\state.json` every 1 s (a
   `DispatcherTimer`), deserialize to the same model shape.
3. **Tray icon reflects status** — swap between pre-rendered `.ico`s (or draw
   with GDI+): green shield (protected), amber shield (blocking / unknown), gray
   slash (not routed), blue eye (monitor). This mirrors the SF Symbol + tint
   logic in `GuardStatus`.
4. **Flyout window** on left-click: the same sections — location card, guard
   toggles, and the usage panel (session / weekly headroom bar / by-model bars
   incl. Fable / 7-day sparkline). Data binding over the deserialized state.
5. **Controls** write command files atomically (write `*.tmp`, then
   `File.Move` → `*.json` in the `cmd` dir) — byte-identical protocol to the
   Swift app.
6. **Quit confirmation (Cmd-Q analog):** intercept the tray "Quit" menu item
   and window close; show a `MessageBox`:
   *"Quit Geo Guard? This turns the guard off and restores Claude to a direct
   connection."* On confirm, send `{"cmd":"quit"}`, wait ~1.2 s for the daemon
   to `route_off`, then exit. Bind to the app-level accelerator so the flyout,
   when focused, treats a close as this same confirmed-quit.

### JSON model
Reuse the field names verbatim (`guard`, `location`, `usage.byModel`,
`usage.headroom`, …). `System.Text.Json` with `[JsonPropertyName("guard")]`
handles the `guard` reserved-word case (same trick as Swift's `CodingKeys`).

---

## 4. Terminal dashboard

`curses` is **not** in the Windows stdlib. Two options:

- **Recommended (dep-free):** rewrite the render loop using **ANSI escape codes**
  (Windows Terminal and modern conhost support VT sequences once you enable
  `ENABLE_VIRTUAL_TERMINAL_PROCESSING` via `SetConsoleMode`) and read keys with
  **`msvcrt.getwch()`** (non-blocking via `msvcrt.kbhit()`). The existing
  `geo-guard-tui.py` layout logic (formatting helpers, bars, sparkline, status
  colors) is reusable almost verbatim; only the `curses` calls (`addstr`,
  `getch`, color pairs) get swapped for an ANSI writer + `msvcrt` input.
- **Fastest to port:** `pip install windows-curses` and run the existing TUI
  nearly unchanged. Adds one dependency; acceptable if you don't mind pip.

Enable VT once at startup:
```python
import ctypes
k = ctypes.windll.kernel32
h = k.GetStdHandle(-11)
mode = ctypes.c_uint()
k.GetConsoleMode(h, ctypes.byref(mode))
k.SetConsoleMode(h, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
```

Ship a `Geo Guard (Terminal).cmd` (the analog of the `.command` file) that runs
`python geo-guard-tui.py`.

---

## 5. Packaging & distribution

- **Tray app:** `dotnet publish -c Release -r win-x64 --self-contained` → a
  single `.exe` (no .NET install required on the target).
- **Daemon:** either (a) require Python 3.9+ on `PATH`, or (b) bundle an
  embeddable Python and invoke it from the tray app. (a) matches how the macOS
  build depends on system `python3`.
- **Installer:** **Inno Setup** (simple) or **MSIX** (Store-friendly). It should:
  - lay down `geoguardd.py`, `_win.py`, `geo-guard-tui.py`, `GeoGuard.exe`, icons;
  - optionally add a **Startup** shortcut / `HKCU\...\Run` key so the guard
    starts at login (mirrors a macOS Login Item);
  - create Start-menu entries for the tray app and the terminal dashboard.
- **Autostart:** Startup folder shortcut is the least-surprising choice; Task
  Scheduler if you want it to survive per-user without a visible shortcut.

---

## 6. Safety invariants to preserve (do not regress)

These are the properties we verified on macOS; the Windows port must keep them:

1. **Never route Claude at a dead proxy.** `route_on()` already refuses unless
   `proxy_is_up()` — keep this check; it is platform-neutral.
2. **Always un-route on shutdown.** The `finally: route_off()` block must run on
   every clean exit, including the `{"cmd":"quit"}` path used by the tray app.
3. **A crashed UI must not break Claude.** If the tray app dies, the daemon keeps
   running with the proxy still up, so routed traffic still flows; and if the
   daemon dies, its `finally` removes routing. The dangerous state
   (settings point at a dead proxy) is unreachable.
4. **Atomic writes** for `state.json`, `settings.json`, and command files
   (`os.replace` / `File.Move`) so no reader ever sees a half-written file.

---

## 7. Suggested build order (phased)

1. **Daemon port** — add `_win.py` (mutex, keep-awake, VT), guard the four Unix
   edges, and confirm `state.json` / `cmd/` work on Windows. Verify the safety
   invariants with the same isolated-`%USERPROFILE%` smoke test we used on macOS.
2. **Terminal TUI** — ANSI + `msvcrt` rewrite (or `windows-curses`). Fastest way
   to see live data and exercise commands before building the GUI.
3. **Tray app** — C#/.NET `NotifyIcon` + flyout, status icons, controls, quit
   confirmation.
4. **Packaging** — Inno Setup/MSIX, autostart, Start-menu entries.
5. **Sign** the `.exe`/installer (Authenticode) to avoid SmartScreen warnings —
   the Windows analog of the macOS ad-hoc/`codesign` step.

Estimated effort: daemon shim ~0.5 day, TUI ~0.5 day, tray app ~2–3 days
(the bulk), packaging ~1 day.
