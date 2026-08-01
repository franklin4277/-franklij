"""Orchestrator - pluggable strategy for running an Agent.

Default implementation: ReAct (Thought → Action → Observation loop).
Future: PlanExecute, Reflection, etc.
"""
from __future__ import annotations

import logging
from typing import AsyncIterator, Protocol

from .events import (
    AgentCompletedEvent,
    AgentEvent,
    AgentErrorEvent,
    AgentStartedEvent,
    AgentStepEvent,
    AgentThoughtEvent,
)

logger = logging.getLogger(__name__)


class Orchestrator(Protocol):
    """Strategy interface for driving an Agent."""

    async def run(self, agent, message: str, **opts) -> str:
        """Run a task to completion. Returns final answer string."""
        ...

    async def stream(self, agent, message: str, **opts) -> AsyncIterator[AgentEvent]:
        """Stream events. Sub-agent events forwarded inline with source tag."""
        ...


class ReActOrchestrator:
    """Default: Thought → Action → Observation loop.

    Works with any Agent that has:
    - .llm (LLMClient with .generate(messages, tools))
    - .messages (list[Message])
    - .tools (dict[name, Tool])
    - .execute_tool(tool_call) -> await ToolResult
    """

    def __init__(self, max_steps: int = 50):
        self.max_steps = max_steps

    async def run(self, agent, message: str, **opts) -> str:
        """Run sync. Returns final answer (no events)."""
        result = None
        async for ev in self.stream(agent, message, **opts):
            if isinstance(ev, AgentCompletedEvent):
                result = ev.final_result
            elif isinstance(ev, AgentErrorEvent) and not ev.recoverable:
                result = f"[Error] {ev.error}"
        return result or ""

    async def stream(self, agent, message, **opts) -> AsyncIterator[AgentEvent]:
        """ReAct loop: think → act → observe, until done or max_steps."""
        yield AgentStartedEvent(task=message, source="main")

        for step in range(self.max_steps):
            # Call LLM
            try:
                tool_list = list(agent.tools.values())
                response = await agent.llm.generate(
                    messages=agent.messages, tools=tool_list
                )
            except Exception as e:
                logger.exception("LLM call failed")
                yield AgentErrorEvent(error=str(e), recoverable=False)
                return

            # Emit thinking
            if getattr(response, "thinking", None):
                yield AgentThoughtEvent(content=response.thinking, source="main")

            # No tool calls → done
            tool_calls = getattr(response, "tool_calls", None) or []
            if not tool_calls:
                # Append final assistant message to history (for multi-turn)
                agent.messages.append(self._build_assistant_msg(response))
                yield AgentCompletedEvent(
                    final_result=getattr(response, "content", "") or "",
                    source="main",
                )
                return

            # Append assistant message
            agent.messages.append(self._build_assistant_msg(response))

            # Execute each tool call
            for tc in tool_calls:
                yield AgentStepEvent(
                    step_number=step + 1,
                    description=f"调用 {tc.function.name}",
                    tool_name=tc.function.name,
                    tool_args=tc.function.arguments,
                    source="main",
                )
                try:
                    result = await agent.execute_tool(tc)
                    preview = self._preview_result(result)
                    yield AgentStepEvent(
                        step_number=step + 1,
                        tool_name=tc.function.name,
                        tool_result_preview=preview,
                        source="main",
                    )
                except Exception as e:
                    logger.exception(f"tool {tc.function.name} failed")
                    yield AgentErrorEvent(
                        error=f"{tc.function.name}: {e}",
                        recoverable=True,
                        source="main",
                    )
                    result = None

                # Append tool result to messages
                agent.messages.append(
                    self._build_tool_result_msg(tc, result)
                )

        # Exhausted max_steps
        yield AgentErrorEvent(
            error=f"max steps reached ({self.max_steps})",
            recoverable=True,
            source="main",
        )

    # ----- helpers (compatible with existing Message + ToolResult shapes) -----

    def _build_assistant_msg(self, response) -> object:
        """Build assistant message from LLM response."""
        # Lazy import to avoid circular
        from ..schema import Message

        return Message(
            role="assistant",
            content=getattr(response, "content", "") or "",
            thinking=getattr(response, "thinking", None),
            tool_calls=getattr(response, "tool_calls", None),
        )

    def _build_tool_result_msg(self, tc, result) -> object:
        """Build tool result message."""
        from ..schema import Message

        content = ""
        if result is not None:
            if hasattr(result, "content"):
                content = result.content or ""
            elif hasattr(result, "error"):
                content = f"Error: {result.error}"
        return Message(
            role="tool",
            content=content,
            tool_call_id=getattr(tc, "id", None),
        )

    def _preview_result(self, result) -> str:
        if result is None:
            return "(no result)"
        s = ""
        if hasattr(result, "content") and result.content:
            s = result.content
        elif hasattr(result, "error") and result.error:
            s = f"Error: {result.error}"
        s = s.replace("\n", " ")[:200]
        return s


__all__ = ["Orchestrator", "ReActOrchestrator"]
