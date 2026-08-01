"""Event types emitted during agent execution.

Used by Orchestrator.stream() for streaming UI / observability.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class AgentEvent:
    """Base event."""
    type: str = "event"
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    source: str = "main"  # "main" | <skill_name>


@dataclass
class AgentStartedEvent(AgentEvent):
    """Task started."""
    type: str = "started"
    task: str = ""


@dataclass
class AgentThoughtEvent(AgentEvent):
    """LLM thinking / reasoning content."""
    type: str = "thought"
    content: str = ""


@dataclass
class AgentStepEvent(AgentEvent):
    """A step (tool call or phase marker).

    Three uses:
    1. Before tool call: tool_name/tool_args filled, tool_result_preview empty
    2. After tool call: tool_result_preview filled
    3. Phase marker: tool_name empty, description describes the step
    """
    type: str = "step"
    step_number: int = 0
    description: str = ""
    tool_name: str | None = None
    tool_args: dict | None = None
    tool_result_preview: str | None = None


@dataclass
class AgentCompletedEvent(AgentEvent):
    """Task completed."""
    type: str = "completed"
    final_result: str = ""


@dataclass
class AgentErrorEvent(AgentEvent):
    """Non-fatal error (execution may continue)."""
    type: str = "error"
    error: str = ""
    recoverable: bool = True


__all__ = [
    "AgentEvent",
    "AgentStartedEvent",
    "AgentThoughtEvent",
    "AgentStepEvent",
    "AgentCompletedEvent",
    "AgentErrorEvent",
]
