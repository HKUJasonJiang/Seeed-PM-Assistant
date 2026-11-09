@echo off
setlocal DisableDelayedExpansion
call "%~dp0Start Assistant.cmd" %*
exit /b %errorlevel%
