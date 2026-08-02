#!/usr/bin/env bash
# 启动官方 GitHub MCP server（Docker，streamable HTTP，端口 8002）
#
# 用法：
#   GITHUB_MCP_TOKEN=github_pat_... bash scripts/start-github-mcp.sh
#
# token 只从环境变量读取，不会写入任何文件。

set -e

if [ -z "${GITHUB_MCP_TOKEN:-}" ]; then
  echo "❌ 未设置 GITHUB_MCP_TOKEN 环境变量。请用:"
  echo "   GITHUB_MCP_TOKEN=github_pat_... bash scripts/start-github-mcp.sh"
  exit 1
fi

NAME="github-mcp-server"
PORT="${GITHUB_MCP_PORT:-8082}"

# 幂等：先停旧容器
if docker ps -a --format '{{.Names}}' | grep -q "^${NAME}$"; then
  echo "[stop] removing existing container ${NAME}…"
  docker rm -f "${NAME}" >/dev/null
fi

echo "[start] launching GitHub MCP server on :${PORT}…"
docker run -d --name "${NAME}" \
  -p "${PORT}:${PORT}" \
  -e GITHUB_PERSONAL_ACCESS_TOKEN="${GITHUB_MCP_TOKEN}" \
  -e DISABLE_EDITOR=true \
  -e DISABLE_ORGANIZATIONS=true \
  ghcr.io/github/github-mcp-server:latest \
  http --port "${PORT}" >/dev/null

echo "✅ GitHub MCP server running:"
echo "   Endpoint: http://localhost:${PORT}/mcp"
echo "   Verify:   curl -s http://localhost:${PORT}/mcp"
