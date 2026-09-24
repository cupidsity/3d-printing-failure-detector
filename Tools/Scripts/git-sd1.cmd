@echo off
rem windows has no shebang line, so this is what `git-sd1` resolves to on the
rem path. it finds a python and hands it the real script, which lives next to
rem this file. `py -c ""` is the check rather than `where python`, because the
rem microsoft store puts a stub named python.exe on the path that fails when run.
setlocal
set "script=%~dp0git-sd1"

py -3 -c "" >nul 2>&1
if not errorlevel 1 goto run_py
python -c "" >nul 2>&1
if not errorlevel 1 goto run_python
python3 -c "" >nul 2>&1
if not errorlevel 1 goto run_python3

echo git-sd1: no python 3 found. install it from python.org, tick "add python to PATH",>&2
echo and reopen your terminal.>&2
exit /b 1

:run_py
py -3 "%script%" %*
exit /b %errorlevel%

:run_python
python "%script%" %*
exit /b %errorlevel%

:run_python3
python3 "%script%" %*
exit /b %errorlevel%
