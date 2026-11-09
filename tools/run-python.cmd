@echo off
setlocal DisableDelayedExpansion
set "seeed_check=import sys,struct; sys.exit(0 if sys.implementation.name=='cpython' and sys.version_info[:2] in ((3,12),(3,13)) and struct.calcsize('P')==8 else 1)"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -I -B -c "%seeed_check%" >nul 2>nul
    if not errorlevel 1 goto private
)
where py >nul 2>nul
if errorlevel 1 goto pathpython
py -3.13 -I -B -c "%seeed_check%" >nul 2>nul
if not errorlevel 1 goto py313
py -3.12 -I -B -c "%seeed_check%" >nul 2>nul
if not errorlevel 1 goto py312
py -3 -I -B -c "%seeed_check%" >nul 2>nul
if not errorlevel 1 goto py3
:pathpython
where python >nul 2>nul
if errorlevel 1 goto missing
python -I -B -c "%seeed_check%" >nul 2>nul
if errorlevel 1 goto missing
python -I -B %*
exit /b %errorlevel%
:private
".venv\Scripts\python.exe" -I -B %*
exit /b %errorlevel%
:py313
py -3.13 -I -B %*
exit /b %errorlevel%
:py312
py -3.12 -I -B %*
exit /b %errorlevel%
:py3
py -3 -I -B %*
exit /b %errorlevel%
:missing
echo Install 64-bit Python 3.12 or 3.13 from https://www.python.org/downloads/windows/
echo In the installer enable "Add python.exe to PATH", then reopen this launcher.
exit /b 1
