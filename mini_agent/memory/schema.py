"""Memory data models for the three-layer memory system."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class MemoryEntry(BaseModel):
    """A single memory entry with confidence scoring."""

    id: str
    content: str
    category: str = "general"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: Literal["core", "learned", "ephemeral"] = "ephemeral"


class MemoryStore(BaseModel):
    """Container for a list of memory entries with serialization helpers."""

    entries: list[MemoryEntry] = Field(default_factory=list)

    def to_dicts(self) -> list[dict]:
        """Serialize entries to list of dicts for JSON storage."""
        return [entry.model_dump() for entry in self.entries]

    @classmethod
    def from_dicts(cls, data: list[dict]) -> "MemoryStore":
        """Deserialize from list of dicts."""
        return cls(entries=[MemoryEntry(**item) for item in data])

    @classmethod
    def load_from_file(cls, filepath: Path) -> "MemoryStore":
        """Load memory store from a JSON file. Returns empty store if file doesn't exist."""
        if not filepath.exists():
            return cls()
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            return cls.from_dicts(data)
        except (json.JSONDecodeError, KeyError):
            return cls()

    def save_to_file(self, filepath: Path) -> None:
        """Save memory store to a JSON file, creating parent directories as needed."""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(
            json.dumps(self.to_dicts(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
