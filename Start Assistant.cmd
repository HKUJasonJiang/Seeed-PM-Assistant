@echo off
setlocal DisableDelayedExpansion
pushd "%~dp0" || exit /b 1
call tools\run-python.cmd tools\bootstrap.py %*
set "seeed_rc=%errorlevel%"
popd
if not "%seeed_rc%"=="0" if "%~1"=="" pause
exit /b %seeed_rc%
