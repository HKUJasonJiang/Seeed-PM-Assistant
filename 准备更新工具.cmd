@echo off
setlocal DisableDelayedExpansion
call "%~dp0Prepare Data Tools.cmd" %*
exit /b %errorlevel%
