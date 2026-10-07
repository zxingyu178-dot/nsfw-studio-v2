@echo off
rem NSFW Studio V2 - 启动后端开发服务器（首次运行自动创建虚拟环境）
setlocal
cd /d "%~dp0..\backend"

if not exist "..\.venv\Scripts\python.exe" (
  echo [NSFW Studio] 首次运行：创建虚拟环境并安装依赖...
  python -m venv "..\.venv" || (echo 虚拟环境创建失败 & pause & exit /b 1)
  "..\.venv\Scripts\python.exe" -m pip install -r requirements.txt || (echo 依赖安装失败 & pause & exit /b 1)
)

"..\.venv\Scripts\python.exe" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
