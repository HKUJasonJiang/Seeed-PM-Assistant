@echo off
setlocal DisableDelayedExpansion
call "%~dp0Start Diagnostics.cmd" %*
exit /b %errorlevel%
