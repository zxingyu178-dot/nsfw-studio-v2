@echo off
rem NSFW Studio V2 - 本机一键启动（生产构建预览模式）
rem   1) 后端 FastAPI（uvicorn，127.0.0.1:8000）
rem   2) 前端生产产物静态服务（vite preview，127.0.0.1:4173，/api 代理到 8000）
rem   3) 自动打开默认浏览器
rem 按项目规则：均为手动临时启动，非常驻服务、不接入 ControlHub。
setlocal
chcp 936 >nul
set "ROOT=%~dp0.."
set "BACKEND=%ROOT%\backend"
set "FRONTEND=%ROOT%\frontend"
set "PYEXE=%ROOT%\.venv\Scripts\python.exe"

rem ---- 后端虚拟环境（首次自动创建）----
if exist "%PYEXE%" goto :venv_ok
where python >nul 2>nul
if errorlevel 1 (
  echo [NSFW Studio] 未找到 Python，请安装 Python 3.11+ 并加入 PATH。
  goto :fail
)
echo [NSFW Studio] 首次运行：创建虚拟环境并安装后端依赖...
python -m venv "%ROOT%\.venv"
if errorlevel 1 goto :fail
"%PYEXE%" -m pip install -r "%BACKEND%\requirements.txt"
if errorlevel 1 goto :fail
:venv_ok

rem ---- Node 解析：AIHome managed-tools 优先，其次系统 PATH ----
set "NODE_DIR="
if defined AIHOME_ROOT if exist "%AIHOME_ROOT%\environment\managed-tools\node" for /d %%D in ("%AIHOME_ROOT%\environment\managed-tools\node\node-*") do set "NODE_DIR=%%D"
if not defined NODE_DIR if exist "D:\AIHome_2.0_L1_L2\environment\managed-tools\node" for /d %%D in ("D:\AIHome_2.0_L1_L2\environment\managed-tools\node\node-*") do set "NODE_DIR=%%D"
if defined NODE_DIR set "PATH=%NODE_DIR%;%PATH%"

where node >nul 2>nul
if errorlevel 1 (
  echo [NSFW Studio] 未找到 Node.js，可设置 AIHOME_ROOT 或安装 Node.js 18+ 到 PATH。
  goto :fail
)

rem ---- 前端依赖（首次自动安装）----
if exist "%FRONTEND%\node_modules" goto :deps_ok
echo [NSFW Studio] 首次运行：安装前端依赖...
pushd "%FRONTEND%"
call npm install --no-audit --no-fund
set "NPMERR=%ERRORLEVEL%"
popd
if not "%NPMERR%"=="0" goto :fail
:deps_ok

rem ---- 前端生产产物（缺失才构建）----
if exist "%FRONTEND%\dist\index.html" goto :dist_ok
echo [NSFW Studio] 构建前端生产产物...
pushd "%FRONTEND%"
call npm run build
set "NPMERR=%ERRORLEVEL%"
popd
if not "%NPMERR%"=="0" goto :fail
:dist_ok

rem ---- 启动后端与前端（各自独立窗口）----
echo [NSFW Studio] 启动后端 http://127.0.0.1:8000 ...
start "NSFW Studio Backend" /D "%BACKEND%" "%PYEXE%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
echo [NSFW Studio] 启动前端 http://127.0.0.1:4173 ...
start "NSFW Studio Frontend" /D "%FRONTEND%" cmd /k "npm run preview"

rem ---- 等待服务就绪后打开浏览器（ping 计时，兼容无控制台环境）----
echo [NSFW Studio] 等待服务就绪并打开浏览器...
ping -n 7 127.0.0.1 >nul
start "" "http://127.0.0.1:4173"
echo [NSFW Studio] 已启动；关闭弹出的两个窗口即可停止程序。
endlocal
exit /b 0

:fail
echo [NSFW Studio] 启动失败，请根据上方提示处理。
pause
exit /b 1
