@echo off
rem ============================================================
rem NSFW Studio V2 - one-click stop thin wrapper.
rem Delegates to stop_studio.ps1 and propagates its exit code.
rem ============================================================
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_studio.ps1" %*
exit /b %ERRORLEVEL%
