"""SubAgent - independently-runnable agent invoked as a Tool.

Future use case: data_analysis_report sub-agent.
"""
from __future__ import annotations

import logging
from typing import AsyncIterator, Protocol

from .events import AgentEvent
from ..tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)


class SubAgent(Protocol):
    """An independently-runnable agent invoked as a Tool.

    Different from Skill:
    - Skill = a bundle of tools (no own LLM loop)
    - SubAgent = has its own Orchestrator + LLM loop
    """

    name: str
    description: str  # shown to LLM when deciding to invoke

    async def run(self, **kwargs) -> str:
        """Execute and return final result as a string."""
        ...

    async def stream(self, **kwargs) -> AsyncIterator[AgentEvent]:
        """Stream events for live UI updates."""
        ...


class SubAgentTool(Tool):
    """Wrap a SubAgent as a Tool for the parent Agent's LLM.

    Each SubAgent becomes a callable tool named after the sub-agent.
    """

    def __init__(self, sub_agent: SubAgent):
        self._sub = sub_agent

    @property
    def name(self) -> str:
        return f"ask_{self._sub.name}"

    @property
    def description(self) -> str:
        return self._sub.description

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "input": {
                    "type": "string",
                    "description": "Task or question for the sub-agent",
                },
            },
            "required": ["input"],
        }

    async def execute(self, *, input: str, **kwargs) -> ToolResult:
        try:
            result = await self._sub.run(input=input, **kwargs)
            return ToolResult(success=True, content=result)
        except Exception as e:
            logger.exception(f"sub-agent {self._sub.name} failed")
            return ToolResult(success=False, error=str(e))


__all__ = ["SubAgent", "SubAgentTool"]
