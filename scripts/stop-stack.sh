#!/usr/bin/env bash
# 停止 API + Web
pkill -f "uvicorn apps.api.data_agent_api" 2>/dev/null && echo "[stop] API killed" || true
pkill -f "next dev" 2>/dev/null && echo "[stop] Web killed" || true