"""Test cases for three-layer memory system."""

import tempfile
from pathlib import Path

import pytest

from mini_agent.memory.manager import MemoryManager
from mini_agent.memory.schema import MemoryEntry, MemoryStore
from mini_agent.memory.tools import CoreMemoryTool, EphemeralMemoryTool, LearnedMemoryTool


# ---------------------------------------------------------------------------
# MemoryEntry & MemoryStore
# ---------------------------------------------------------------------------

def test_memory_entry_creation():
    """Test creating a MemoryEntry with default values."""
    entry = MemoryEntry(id="test_1", content="Hello world", source="ephemeral")
    assert entry.id == "test_1"
    assert entry.content == "Hello world"
    assert entry.category == "general"
    assert entry.confidence == 1.0
    assert entry.source == "ephemeral"

def test_memory_entry_confidence_bounds():
    """Test confidence is clamped to 0.0-1.0."""
    entry = MemoryEntry(id="t", content="x", confidence=0.5, source="learned")
    assert entry.confidence == 0.5
    with pytest.raises(Exception):
        MemoryEntry(id="t", content="x", confidence=-0.1, source="learned")
    with pytest.raises(Exception):
        MemoryEntry(id="t", content="x", confidence=1.5, source="learned")

def test_memory_store_roundtrip():
    """Test serialization round-trip."""
    store = MemoryStore()
    store.entries.append(MemoryEntry(id="a", content="one", source="core"))
    store.entries.append(MemoryEntry(id="b", content="two", source="learned", confidence=0.8))
    dicts = store.to_dicts()
    restored = MemoryStore.from_dicts(dicts)
    assert len(restored.entries) == 2
    assert restored.entries[0].content == "one"
    assert restored.entries[1].confidence == 0.8

def test_memory_store_file_persistence():
    """Test saving and loading from file."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
        filepath = Path(f.name)

    try:
        store = MemoryStore()
        store.entries.append(MemoryEntry(id="x", content="persisted", source="learned"))
        store.save_to_file(filepath)

        reloaded = MemoryStore.load_from_file(filepath)
        assert len(reloaded.entries) == 1
        assert reloaded.entries[0].content == "persisted"
    finally:
        filepath.unlink(missing_ok=True)

def test_memory_store_load_missing_file():
    """Test loading from a non-existent file returns empty store."""
    store = MemoryStore.load_from_file(Path("/nonexistent/memory.json"))
    assert len(store.entries) == 0


# ---------------------------------------------------------------------------
# MemoryManager
# ---------------------------------------------------------------------------

def test_memory_manager_core_readonly():
    """Test CORE memories can be read but have no write method."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
        f.write('[{"id":"c1","content":"rule","category":"safety","confidence":1.0,"source":"core"}]')
        core_path = f.name

    try:
        mgr = MemoryManager(core_memory_path=core_path)
        entries = mgr.get_core_memories()
        assert len(entries) == 1
        assert entries[0].content == "rule"
    finally:
        Path(core_path).unlink(missing_ok=True)

def test_memory_manager_core_filter_by_category():
    """Test filtering CORE memories by category."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
        f.write('[{'
                '"id":"c1","content":"safety rule","category":"safety","confidence":1.0,"source":"core"},'
                '{"id":"c2","content":"convention","category":"convention","confidence":1.0,"source":"core"}'
                ']')
        core_path = f.name

    try:
        mgr = MemoryManager(core_memory_path=core_path)
        safety = mgr.get_core_memories(category="safety")
        assert len(safety) == 1
        assert safety[0].content == "safety rule"
    finally:
        Path(core_path).unlink(missing_ok=True)

def test_memory_manager_learned_confidence_gating():
    """Test LEARNED writes above threshold succeed, below fail."""
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = MemoryManager(learned_memory_dir=tmpdir, learned_confidence_threshold=0.7)

        accepted, reason = mgr.record_learned("high confidence", confidence=0.9, category="test")
        assert accepted
        assert "Recorded" in reason

        accepted, reason = mgr.record_learned("low confidence", confidence=0.3, category="test")
        assert not accepted
        assert "below threshold" in reason

        entries = mgr.get_learned_memories()
        assert len(entries) == 1
        assert entries[0].content == "high confidence"

def test_memory_manager_learned_persistence():
    """Test LEARNED memories persist across manager instances."""
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr1 = MemoryManager(learned_memory_dir=tmpdir)
        mgr1.record_learned("persist", confidence=0.8)

        mgr2 = MemoryManager(learned_memory_dir=tmpdir)
        entries = mgr2.get_learned_memories()
        assert len(entries) == 1
        assert entries[0].content == "persist"

def test_memory_manager_ephemeral_scope():
    """Test EPHEMERAL record/recall works, reset clears."""
    mgr = MemoryManager()
    mgr.record_ephemeral("temp data", category="session")
    mgr.record_ephemeral("more temp", category="session")

    entries = mgr.get_ephemeral()
    assert len(entries) == 2

    mgr.reset_ephemeral()
    assert len(mgr.get_ephemeral()) == 0

def test_memory_manager_ephemeral_empty():
    """Test EPHEMERAL returns empty when no entries."""
    mgr = MemoryManager()
    assert len(mgr.get_ephemeral()) == 0


# ---------------------------------------------------------------------------
# Memory Tools
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_core_memory_tool():
    """Test CoreMemoryTool returns CORE memories."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
        f.write('[{"id":"c1","content":"core rule","category":"safety","confidence":1.0,"source":"core"}]')
        core_path = f.name

    try:
        mgr = MemoryManager(core_memory_path=core_path)
        tool = CoreMemoryTool(mgr)
        result = await tool.execute()
        assert result.success
        assert "core rule" in result.content
    finally:
        Path(core_path).unlink(missing_ok=True)

@pytest.mark.asyncio
async def test_learned_memory_tool_recall():
    """Test LearnedMemoryTool recall action."""
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = MemoryManager(learned_memory_dir=tmpdir)
        mgr.record_learned("pattern A", confidence=0.85)
        mgr.record_learned("pattern B", confidence=0.75)

        tool = LearnedMemoryTool(mgr)
        result = await tool.execute(action="recall")
        assert result.success
        assert "pattern A" in result.content
        assert "pattern B" in result.content

@pytest.mark.asyncio
async def test_learned_memory_tool_record_success():
    """Test LearnedMemoryTool record with high confidence succeeds."""
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = MemoryManager(learned_memory_dir=tmpdir, learned_confidence_threshold=0.7)
        tool = LearnedMemoryTool(mgr)

        result = await tool.execute(action="record", content="new pattern", confidence=0.9)
        assert result.success
        assert "Recorded" in result.content

@pytest.mark.asyncio
async def test_learned_memory_tool_record_rejected():
    """Test LearnedMemoryTool record with low confidence fails."""
    mgr = MemoryManager(learned_confidence_threshold=0.7)
    tool = LearnedMemoryTool(mgr)

    result = await tool.execute(action="record", content="weak pattern", confidence=0.4)
    assert not result.success
    assert "below threshold" in result.content

@pytest.mark.asyncio
async def test_learned_memory_tool_record_missing_content():
    """Test LearnedMemoryTool record fails without content."""
    mgr = MemoryManager()
    tool = LearnedMemoryTool(mgr)
    result = await tool.execute(action="record", content="")
    assert not result.success
    assert "content" in result.error.lower()

@pytest.mark.asyncio
async def test_ephemeral_memory_tool():
    """Test EphemeralMemoryTool record and recall."""
    mgr = MemoryManager()
    tool = EphemeralMemoryTool(mgr)

    result = await tool.execute(action="record", content="session data")
    assert result.success
    assert "Recorded" in result.content

    result = await tool.execute(action="recall")
    assert result.success
    assert "session data" in result.content

@pytest.mark.asyncio
async def test_ephemeral_memory_tool_reset():
    """Test EphemeralMemoryTool recall after reset returns empty."""
    mgr = MemoryManager()
    tool = EphemeralMemoryTool(mgr)
    await tool.execute(action="record", content="temp")
    mgr.reset_ephemeral()

    result = await tool.execute(action="recall")
    assert result.success
    assert "No memories found" in result.content

@pytest.mark.asyncio
async def test_ephemeral_memory_tool_missing_content():
    """Test EphemeralMemoryTool record fails without content."""
    mgr = MemoryManager()
    tool = EphemeralMemoryTool(mgr)
    result = await tool.execute(action="record", content="")
    assert not result.success
    assert "content" in result.error.lower()
