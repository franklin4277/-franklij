"""Schema types — was mini_agent/schema/schema.py (single file)."""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel


class LLMProvider(str, Enum):
    """LLM provider types."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"


class FunctionCall(BaseModel):
    """Function call details."""

    name: str
    arguments: dict[str, Any]


class ToolCall(BaseModel):
    """Tool call structure."""

    id: str
    type: str  # "function"
    function: FunctionCall


class Message(BaseModel):
    """Chat message."""

    role: str  # "system" | "user" | "assistant" | "tool"
    content: str | list[dict[str, Any]]
    thinking: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None


class TokenUsage(BaseModel):
    """Token usage from LLM response."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class LLMResponse(BaseModel):
    """LLM response."""

    content: str
    thinking: str | None = None
    tool_calls: list[ToolCall] | None = None
    finish_reason: str
    usage: TokenUsage | None = None


__all__ = [
    "LLMProvider",
    "FunctionCall",
    "ToolCall",
    "Message",
    "TokenUsage",
    "LLMResponse",
]