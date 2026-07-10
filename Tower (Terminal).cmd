@echo off
REM Double-click to open the Tower terminal dashboard (TUI) on Windows.
REM Same guard, same live data as the (macOS) menubar app — just in your terminal.
setlocal
set "HERE=%~dp0"
set "TUI=%HERE%Tower.app\Contents\Resources\tower-tui.py"
if not exist "%TUI%" set "TUI=%HERE%src\tower-tui.py"

REM Prefer the py launcher, fall back to python on PATH.
where py >nul 2>nul
if %errorlevel%==0 (
  py "%TUI%"
) else (
  python "%TUI%"
)
endlocal
