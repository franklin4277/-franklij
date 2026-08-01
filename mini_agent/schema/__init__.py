"""Backward-compat shim. Use mini_agent.schema instead.

Old code path: `from mini_agent.schema import Message`
New code path: same (re-exported from new single-file schema)
"""
from .schema import (  # noqa: F401
    FunctionCall,
    LLMProvider,
    LLMResponse,
    Message,
    TokenUsage,
    ToolCall,
)

__all__ = [
    "FunctionCall",
    "LLMProvider",
    "LLMResponse",
    "Message",
    "TokenUsage",
    "ToolCall",
]