@echo off
rem ============================================================
rem NSFW Studio V2 - thin launcher wrapper.
rem Delegates to launch_studio.ps1, forwards all arguments, and
rem propagates its exit code. The PowerShell script locates the
rem project root on its own (this .bat lives next to it in scripts\).
rem ============================================================
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_studio.ps1" %*
exit /b %ERRORLEVEL%
