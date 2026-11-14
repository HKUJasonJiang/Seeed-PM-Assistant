@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul 2>nul
call "%~dp0Start Assistant.cmd" --diagnose %*
set "seeed_rc=%errorlevel%"
if "%~1"=="" pause
exit /b %seeed_rc%
