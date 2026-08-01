"""FastAPI app entry point.

Run:
    uv run uvicorn mini_agent.api.main:app --host 0.0.0.0 --port 18002
"""
from __future__ import annotations

import logging
import os

import uvicorn
from fastapi import FastAPI

from .deps import lifespan
from .routes import router

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Data Agent API",
        description="HTTP/REST 接口，封装 SQLBot 的 NL2Data 能力。",
        version="0.3.0",
        lifespan=lifespan,
    )
    app.include_router(router)
    return app


app = create_app()


def main():
    port = int(os.environ.get("PORT", "18002"))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"🚀 Data Agent API: http://{host}:{port}")
    print(f"   Docs: http://{host}:{port}/docs")
    uvicorn.run("mini_agent.api.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()