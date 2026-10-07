@echo off
rem NSFW Studio V2 - 启动前端开发服务器
rem Node 解析顺序（Phase 0.1 可移植性收口）：
rem   1) AIHome 统一环境（存在时才使用，自动探测版本子目录）
rem   2) 系统 PATH 中的 Node/npm
rem   3) 都找不到 -> 清晰报错退出
rem 不依赖任何单一固定机器路径。
setlocal enabledelayedexpansion
cd /d "%~dp0..\frontend"

set "AIHOME_NODE_ROOT=D:\AIHome_2.0_L1_L2\environment\managed-tools\node"
set "NODE_DIR="
if exist "%AIHOME_NODE_ROOT%" (
  for /d %%D in ("%AIHOME_NODE_ROOT%\node-*") do set "NODE_DIR=%%D"
)
if defined NODE_DIR (
  echo [NSFW Studio] 使用 AIHome Node: !NODE_DIR!
  set "PATH=!NODE_DIR!;%PATH%"
)

where node >nul 2>nul
if errorlevel 1 (
  echo [NSFW Studio] 未找到 Node.js（AIHome 环境与系统 PATH 均无）。
  echo               请安装 Node.js 18+，或配置 AIHome managed-tools 环境。
  pause & exit /b 1
)

if not exist "node_modules" (
  echo [NSFW Studio] 首次运行：安装前端依赖...
  call npm install --no-audit --no-fund || (echo 依赖安装失败 & pause & exit /b 1)
)

call npm run dev
