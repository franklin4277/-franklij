"""Pydantic models for the Gateway API."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class CreateSessionRequest(BaseModel):
    """Request to create a new session."""
    workspace_dir: Optional[str] = None
    system_prompt: Optional[str] = None

class SessionResponse(BaseModel):
    """Response for session creation."""
    session_id: str
    workspace_dir: str
    created_at: str

class ChatRequest(BaseModel):
    """Request to send a message to the agent."""
    message: str
    stream: bool = False  # Future support for streaming

class ChatResponse(BaseModel):
    """Response from the agent."""
    response: str
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    usage: Optional[Dict[str, int]] = None

class HistoryResponse(BaseModel):
    """Response for chat history."""
    messages: List[Dict[str, Any]]
