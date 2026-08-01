#!/usr/bin/env bash
# 一键启动 API + Web（开发模式）
# 使用：
#   bash scripts/start-stack.sh

set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cleanup() {
  echo ""
  echo "[stop] killing processes…"
  if [ -n "$API_PID" ]; then kill $API_PID 2>/dev/null || true; fi
  if [ -n "$WEB_PID" ]; then kill $WEB_PID 2>/dev/null || true; fi
  exit 0
}
trap cleanup INT TERM

# 1. 启动 API（在 mini_agent 包内）
echo "[start] launching API on :18002…"
cd "$ROOT"
SQLBOT_CONFIG="${SQLBOT_CONFIG:-mini_agent/config/sqlbot-example.yaml}" \
WORKSPACE_DIR="${WORKSPACE_DIR:-$ROOT/workspace_api}" \
PORT=18002 \
uv run uvicorn mini_agent.api.main:app --host 0.0.0.0 --port 18002 &
API_PID=$!
sleep 3

# 2. 启动 Web（在项目根 web/）
echo "[start] launching Web on :13000 (first build will take ~30s)…"
cd "$ROOT/web"
if [ ! -d "node_modules" ]; then
  echo "[start] installing npm deps (this may take a minute)…"
  npm install --no-audit --no-fund
fi
API_PROXY_TARGET=http://localhost:18002 npm run dev &
WEB_PID=$!

echo ""
echo "✅ Data Agent is running:"
echo "   Web:   http://localhost:13000"
echo "   API:   http://localhost:18002"
echo "   Docs:  http://localhost:18002/docs"
echo ""
echo "Press Ctrl+C to stop both."

wait