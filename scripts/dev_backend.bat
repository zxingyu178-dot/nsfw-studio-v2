@echo off
rem NSFW Studio V2 - 启动后端开发服务器（首次运行自动创建虚拟环境）
rem 本脚本不依赖任何固定机器路径；Python 从系统 PATH 解析。
rem
rem 统一入口保护：生产端口 8000 仅由 ControlHub 托管。本开发脚本默认使用
rem 8100，避免出现 ControlHub 无法 stop 的游离 uvicorn 实例。
rem 用法：dev_backend.bat [port]     默认 8100
setlocal
set "PORT=%~1"
if "%PORT%"=="" set "PORT=8100"

if "%PORT%"=="8000" (
  echo [NSFW Studio][DEV] 拒绝启动：生产端口 8000 仅由 ControlHub 托管。
  echo [NSFW Studio][DEV] 启动：scripts\launch_studio.ps1    停止：scripts\stop_studio.ps1
  echo [NSFW Studio][DEV] 开发请用默认端口 8100，并设置 NSFW_STUDIO_API_URL=http://127.0.0.1:8100
  exit /b 2
)

cd /d "%~dp0..\backend"

where python >nul 2>nul
if errorlevel 1 (
  echo [NSFW Studio] 未找到 Python。请安装 Python 3.11+ 并加入 PATH。
  pause & exit /b 1
)

if not exist "..\.venv\Scripts\python.exe" (
  echo [NSFW Studio] 首次运行：创建虚拟环境并安装依赖...
  python -m venv "..\.venv" || (echo 虚拟环境创建失败 & pause & exit /b 1)
  "..\.venv\Scripts\python.exe" -m pip install -r requirements.txt || (echo 依赖安装失败 & pause & exit /b 1)
)

echo [NSFW Studio][DEV] 开发后端：http://127.0.0.1:%PORT% （前端需设 NSFW_STUDIO_API_URL=http://127.0.0.1:%PORT%）
"..\.venv\Scripts\python.exe" -m uvicorn app.main:app --reload --host 127.0.0.1 --port %PORT%
