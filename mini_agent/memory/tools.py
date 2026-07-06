"""Memory tools for the three-layer memory system.

CoreMemoryTool  — Read-only access to CORE memories.
LearnedMemoryTool — Recall + confidence-gated record to LEARNED.
EphemeralMemoryTool — Session-scoped read/write, auto-cleaned.
"""

from typing import Any

from mini_agent.tools.base import Tool, ToolResult

from .manager import MemoryManager
from .schema import MemoryEntry


def _format_entries(entries: list[MemoryEntry]) -> str:
    """Format memory entries for tool output."""
    if not entries:
        return "No memories found."
    lines = []
    for i, entry in enumerate(entries, 1):
        line = (
            f"{i}. [{entry.category}] {entry.content}"
            + "\n"
            + f"   (id: {entry.id}, confidence: {entry.confidence:.2f}, "
            + f"source: {entry.source}, recorded: {entry.timestamp})"
        )
        lines.append(line)
    return "\n".join(lines)


class CoreMemoryTool(Tool):
    """Read-only access to CORE (immutable) project memories."""

    def __init__(self, manager: MemoryManager):
        self._manager = manager

    @property
    def name(self) -> str:
        return "core_memory"

    @property
    def description(self) -> str:
        return (
            "Retrieve immutable CORE project memories (rules, safety constraints, "
            "workspace conventions). Read-only — these cannot be modified at runtime. "
            "Use this to recall project-level rules before making decisions."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Optional: filter core memories by category (e.g., 'safety', 'convention')",
                },
            },
        }

    async def execute(self, category: str | None = None) -> ToolResult:
        entries = self._manager.get_core_memories(category=category)
        return ToolResult(success=True, content=_format_entries(entries))


class LearnedMemoryTool(Tool):
    """Recall and confidence-gated record for LEARNED memories."""

    def __init__(self, manager: MemoryManager):
        self._manager = manager

    @property
    def name(self) -> str:
        return "learned_memory"

    @property
    def description(self) -> str:
        return (
            "Recall or record LEARNED memories — cross-session patterns and discoveries. "
            "Recording requires a confidence score (0.0-1.0); entries below the confidence "
            "threshold are rejected. Use 'recall' to retrieve past learnings, "
            "'record' to store a new pattern with a confidence score."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["recall", "record"],
                    "description": "Action: 'recall' to retrieve, 'record' to store (requires content + confidence).",
                },
                "content": {
                    "type": "string",
                    "description": "For 'record': the memory content. For 'recall': ignored.",
                },
                "category": {
                    "type": "string",
                    "description": "Optional category/tag for filtering or labeling.",
                },
                "confidence": {
                    "type": "number",
                    "description": "For 'record': confidence score (0.0-1.0). Below threshold = rejected.",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        content: str = "",
        category: str = "general",
        confidence: float = 1.0,
    ) -> ToolResult:
        if action == "recall":
            cat = category if category != "general" else None
            entries = self._manager.get_learned_memories(category=cat)
            return ToolResult(success=True, content=_format_entries(entries))

        if action == "record":
            if not content:
                return ToolResult(success=False, content="", error="'content' is required for 'record' action.")
            accepted, reason = self._manager.record_learned(
                content=content, confidence=confidence, category=category
            )
            return ToolResult(success=accepted, content=reason)

        return ToolResult(success=False, content="", error=f"Unknown action: '{action}'. Use 'recall' or 'record'.")


class EphemeralMemoryTool(Tool):
    """Session-scoped read/write for EPHEMERAL memories."""

    def __init__(self, manager: MemoryManager):
        self._manager = manager

    @property
    def name(self) -> str:
        return "ephemeral_memory"

    @property
    def description(self) -> str:
        return (
            "Recall or record EPHEMERAL (session-scoped) memories. Cleared at session end. "
            "Use for temporary context, current task state, and one-off facts. "
            "Use 'recall' to retrieve, 'record' to store."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["recall", "record"],
                    "description": "Action: 'recall' to retrieve, 'record' to store.",
                },
                "content": {
                    "type": "string",
                    "description": "For 'record': the content to store. For 'recall': ignored.",
                },
                "category": {
                    "type": "string",
                    "description": "Optional category/tag for filtering or labeling.",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        content: str = "",
        category: str = "general",
    ) -> ToolResult:
        if action == "recall":
            cat = category if category != "general" else None
            entries = self._manager.get_ephemeral(category=cat)
            return ToolResult(success=True, content=_format_entries(entries))

        if action == "record":
            if not content:
                return ToolResult(success=False, content="", error="'content' is required for 'record' action.")
            entry = self._manager.record_ephemeral(content=content, category=category)
            return ToolResult(success=True, content=f"Recorded ephemeral memory (id: {entry.id})")

        return ToolResult(success=False, content="", error=f"Unknown action: '{action}'. Use 'recall' or 'record'.")
