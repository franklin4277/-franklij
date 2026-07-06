"""MemoryManager — manages the three-layer memory system.

Layers:
  CORE     — Immutable project rules, loaded from JSON file, read-only.
  LEARNED  — Confidence-gated cross-session patterns, persisted to disk.
  EPHEMERAL — Session-scoped context, in-memory only, cleared on reset.
"""

import uuid
from pathlib import Path

from .schema import MemoryEntry, MemoryStore


class MemoryManager:
    """Manages CORE, LEARNED, and EPHEMERAL memory layers."""

    def __init__(
        self,
        core_memory_path: str | None = None,
        learned_memory_dir: str | None = None,
        learned_confidence_threshold: float = 0.7,
    ):
        self._confidence_threshold = learned_confidence_threshold

        # --- CORE layer ---
        if core_memory_path:
            self._core_path = Path(core_memory_path).expanduser()
        else:
            self._core_path = Path.home() / ".mini-agent" / "memory" / "core.json"
        self._core_store = MemoryStore.load_from_file(self._core_path)

        # --- LEARNED layer ---
        if learned_memory_dir:
            self._learned_path = Path(learned_memory_dir).expanduser() / "learned.json"
        else:
            self._learned_path = Path.home() / ".mini-agent" / "memory" / "learned.json"
        self._learned_store = MemoryStore.load_from_file(self._learned_path)

        # --- EPHEMERAL layer ---
        self._ephemeral_store = MemoryStore()

    # ------------------------------------------------------------------
    # CORE — read-only
    # ------------------------------------------------------------------

    def get_core_memories(self, category: str | None = None) -> list[MemoryEntry]:
        """Retrieve CORE memories, optionally filtered by category."""
        entries = self._core_store.entries
        if category:
            entries = [e for e in entries if e.category == category]
        return entries

    # ------------------------------------------------------------------
    # LEARNED — confidence-gated write + recall
    # ------------------------------------------------------------------

    def get_learned_memories(self, category: str | None = None) -> list[MemoryEntry]:
        """Retrieve LEARNED memories, optionally filtered by category."""
        entries = self._learned_store.entries
        if category:
            entries = [e for e in entries if e.category == category]
        return entries

    def record_learned(
        self, content: str, confidence: float, category: str = "general"
    ) -> tuple[bool, str]:
        """Record a LEARNED memory entry with confidence gating.

        Args:
            content: The memory content to store.
            confidence: Confidence score (0.0-1.0). Must meet threshold.
            category: Optional category tag.

        Returns:
            Tuple of (accepted: bool, reason: str).
        """
        if confidence < self._confidence_threshold:
            return (
                False,
                f"Confidence {confidence:.2f} below threshold {self._confidence_threshold}. "
                "Memory not recorded.",
            )

        entry = MemoryEntry(
            id=str(uuid.uuid4())[:8],
            content=content,
            category=category,
            confidence=confidence,
            source="learned",
        )
        self._learned_store.entries.append(entry)
        self._learned_store.save_to_file(self._learned_path)
        return True, f"Recorded learned memory (confidence: {confidence:.2f})"

    # ------------------------------------------------------------------
    # EPHEMERAL — session-scoped, in-memory
    # ------------------------------------------------------------------

    def get_ephemeral(self, category: str | None = None) -> list[MemoryEntry]:
        """Retrieve EPHEMERAL memories, optionally filtered by category."""
        entries = self._ephemeral_store.entries
        if category:
            entries = [e for e in entries if e.category == category]
        return entries

    def record_ephemeral(self, content: str, category: str = "general") -> MemoryEntry:
        """Record a session-scoped EPHEMERAL memory entry."""
        entry = MemoryEntry(
            id=str(uuid.uuid4())[:8],
            content=content,
            category=category,
            confidence=1.0,
            source="ephemeral",
        )
        self._ephemeral_store.entries.append(entry)
        return entry

    def reset_ephemeral(self) -> None:
        """Clear all EPHEMERAL memories."""
        self._ephemeral_store = MemoryStore()
