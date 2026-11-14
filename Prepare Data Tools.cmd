@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul 2>nul
call "%~dp0Start Assistant.cmd" --install-dependencies %*
set "seeed_rc=%errorlevel%"
if not "%seeed_rc%"=="0" if "%~1"=="" pause
exit /b %seeed_rc%
