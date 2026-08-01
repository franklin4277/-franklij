@echo off
REM 一键启动 API + Web（开发模式，Windows）
REM 用法：scripts\start-stack.bat

setlocal

set "ROOT=%~dp0.."
cd /d "%ROOT%"

echo [start] launching API on :18002...
start "DataAgent-API" /B cmd /c "set SQLBOT_CONFIG=mini_agent\config\sqlbot-example.yaml&& set PORT=18002&& uv run uvicorn mini_agent.api.main:app --host 0.0.0.0 --port 18002"
timeout /t 4 /nobreak >nul

echo [start] launching Web on :13000...
cd /d "%ROOT%\web"
if not exist node_modules (
  echo [start] installing npm deps...
  call npm install --no-audit --no-fund
)
start "DataAgent-Web" /B cmd /c "set API_PROXY_TARGET=http://localhost:18002&& npm run dev"

echo.
echo Data Agent is running:
echo   Web:   http://localhost:13000
echo   API:   http://localhost:18002
echo   Docs:  http://localhost:18002/docs
echo.
echo Run scripts\stop-stack.bat to stop.

endlocal