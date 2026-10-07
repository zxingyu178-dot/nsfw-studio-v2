@echo off
rem NSFW Studio V2 - 启动前端开发服务器
rem Node 解析顺序（Phase 0.1.1 更新，不依赖单一固定机器路径）：
rem   1) AIHOME_ROOT 环境变量指向的 AIHome 环境（存在时才使用）
rem   2) AIHome 全局规范默认根目录（存在时才使用，作兼容探测）
rem   3) 系统 PATH 中的 Node/npm
rem   4) 都找不到 -> 清晰报错退出
setlocal enabledelayedexpansion
cd /d "%~dp0..\frontend"

set "NODE_DIR="
if defined AIHOME_ROOT (
  set "AIHOME_NODE_ROOT=!AIHOME_ROOT!\environment\managed-tools\node"
  if exist "!AIHOME_NODE_ROOT!" (
    for /d %%D in ("!AIHOME_NODE_ROOT!\node-*") do set "NODE_DIR=%%D"
  )
)
if not defined NODE_DIR (
  if exist "D:\AIHome_2.0_L1_L2\environment\managed-tools\node" (
    for /d %%D in ("D:\AIHome_2.0_L1_L2\environment\managed-tools\node\node-*") do set "NODE_DIR=%%D"
  )
)
if defined NODE_DIR (
  echo [NSFW Studio] 使用 AIHome Node: !NODE_DIR!
  set "PATH=!NODE_DIR!;%PATH%"
)

where node >nul 2>nul
if errorlevel 1 (
  echo [NSFW Studio] 未找到 Node.js。
  echo               可设置环境变量 AIHOME_ROOT 指向 AIHome 根目录，
  echo               或安装 Node.js 18+ 到系统 PATH。
  pause & exit /b 1
)

if not exist "node_modules" (
  echo [NSFW Studio] 首次运行：安装前端依赖...
  call npm install --no-audit --no-fund || (echo 依赖安装失败 & pause & exit /b 1)
)

call npm run dev
