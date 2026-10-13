@echo off
rem ============================================================
rem NSFW Studio V2 - LEGACY SHIM.
rem
rem This old entry point is kept by name for backward compat, but it
rem no longer starts the backend web server / frontend preview on its
rem own. Phase 0.14 Runtime Closure makes ControlHub the single
rem production lifecycle owner (fixed 127.0.0.1:8000). This file only
rem forwards to the production launcher:
rem     start_studio.bat  ->  launch_studio.bat  ->  launch_studio.ps1
rem
rem There must be NO self-hosted server startup chain here.
rem ============================================================
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_studio.ps1" %*
exit /b %ERRORLEVEL%
