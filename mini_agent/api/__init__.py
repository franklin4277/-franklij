"""mini_agent.api — FastAPI HTTP/REST for the data agent.

Public entry: `uvicorn mini_agent.api.main:app`
"""
from .main import app, create_app

__all__ = ["app", "create_app"]