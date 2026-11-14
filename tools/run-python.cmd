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
if errorlevel 1 goto installed
python -I -B -c "%seeed_check%" >nul 2>nul
if errorlevel 1 goto installed
python -I -B %*
exit /b %errorlevel%
:installed
for %%v in (313 312) do (
    for %%d in ("%LOCALAPPDATA%\Programs\Python\Python%%v" "%LOCALAPPDATA%\Programs\Python\Python%%v-64" "%ProgramFiles%\Python%%v") do (
        if exist "%%~d\python.exe" (
            "%%~d\python.exe" -I -B -c "%seeed_check%" >nul 2>nul
            if not errorlevel 1 (
                set "seeed_python=%%~d\python.exe"
                goto installedpython
            )
        )
    )
)
goto missing
:installedpython
"%seeed_python%" -I -B %*
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
>startup-diagnostic.txt echo [PYTHON_NOT_FOUND] No supported 64-bit CPython 3.12 or 3.13 was detected.
set "seeed_previous_cp="
for /f "tokens=2 delims=:" %%p in ('chcp 2^>nul') do set "seeed_previous_cp=%%p"
chcp 65001 >nul 2>nul
type "%~dp0python-help.txt"
type "%~dp0python-help.txt" >>startup-diagnostic.txt
if defined seeed_previous_cp chcp %seeed_previous_cp% >nul 2>nul
exit /b 1
