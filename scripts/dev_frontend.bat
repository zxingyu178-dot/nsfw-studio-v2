@echo off
rem NSFW Studio V2 - 启动前端开发服务器（Node 使用 AIHome 统一环境）
setlocal
set "NODE_HOME=D:\AIHome_2.0_L1_L2\environment\managed-tools\node\node-v24.18.1-win-x64"
set "PATH=%NODE_HOME%;%PATH%"
cd /d "%~dp0..\frontend"

if not exist "node_modules" (
  echo [NSFW Studio] 首次运行：安装前端依赖...
  call npm install --no-audit --no-fund || (echo 依赖安装失败 & pause & exit /b 1)
)

call npm run dev
