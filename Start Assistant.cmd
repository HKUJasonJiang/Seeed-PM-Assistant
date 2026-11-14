@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul 2>nul
echo [Seeed] Checking Python and the extracted application...
pushd "%~dp0" || exit /b 1
for %%f in (index.html data\catalog.js tools\run-python.cmd tools\bootstrap.py tools\launch.py tools\startup_report.py) do if not exist "%%f" goto incomplete
call tools\run-python.cmd tools\bootstrap.py %*
set "seeed_rc=%errorlevel%"
goto finish
:incomplete
echo [FILES] Extract the entire ZIP into a writable folder, then open Start Assistant.cmd from that folder.
>startup-diagnostic.txt echo [FILES] Application files are missing. Extract the entire ZIP into a writable folder.
if exist tools\file-help.txt type tools\file-help.txt
if exist tools\file-help.txt type tools\file-help.txt >>startup-diagnostic.txt
set "seeed_rc=1"
:finish
if not "%seeed_rc%"=="0" echo [Seeed] Startup did not finish. Open startup-diagnostic.txt in this folder or run Start Diagnostics.cmd.
popd
if not "%seeed_rc%"=="0" if "%~1"=="" pause
exit /b %seeed_rc%
