"""Integration tests for the MiniMax ACP adapter.

All tests are fully mocked: no stdio transport, no network, no real LLM.
The adapter is driven directly through its ACP entry points
(``initialize`` / ``newSession`` / ``prompt`` / ``cancel``) and the outgoing
``sessionUpdate`` notifications are captured by :class:`DummyConn`.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from mini_agent.acp import MiniMaxACPAgent
from mini_agent.config import AgentConfig, Config, LLMConfig, ToolsConfig
from mini_agent.schema import FunctionCall, LLMResponse, ToolCall
from mini_agent.tools import Tool, ToolResult

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class DummyConn:
    """Captures every SessionNotification the adapter emits."""

    def __init__(self):
        self.updates = []

    async def sessionUpdate(self, payload):
        self.updates.append(payload)

    def of_kind(self, kind):
        """All captured updates whose ``sessionUpdate`` discriminator matches."""
        return [u for u in self.updates if getattr(u.update, "sessionUpdate", None) == kind]


class DummyLLM:
    """Turn 1 asks for ``echo``; turn 2 finishes with plain content."""

    def __init__(self):
        self.calls = 0

    async def generate(self, messages, tools):
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                content="",
                thinking="calling echo",
                tool_calls=[make_tool_call("tool1", "echo", {"text": "ping"})],
                finish_reason="tool",
            )
        return LLMResponse(content="done", thinking=None, tool_calls=None, finish_reason="stop")


class ScriptedLLM:
    """Replays a fixed list of LLMResponses, repeating the last one forever."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = 0
        self.seen_messages = []

    async def generate(self, messages, tools):
        self.seen_messages.append(list(messages))
        index = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        return self.responses[index]


class ExplodingLLM:
    """Always raises, to exercise the mid-turn LLM error path."""

    def __init__(self, message="llm exploded"):
        self.message = message
        self.calls = 0

    async def generate(self, messages, tools):
        self.calls += 1
        raise RuntimeError(self.message)


class CancellingLLM:
    """Cancels its own session during the first turn, then keeps looping."""

    def __init__(self):
        self.adapter = None
        self.session_id = None
        self.calls = 0

    async def generate(self, messages, tools):
        self.calls += 1
        if self.calls == 1:
            await self.adapter.cancel(SimpleNamespace(sessionId=self.session_id))
            return LLMResponse(
                content="",
                thinking=None,
                tool_calls=[make_tool_call("c1", "echo", {"text": "x"})],
                finish_reason="tool",
            )
        return LLMResponse(content="should not be reached", thinking=None, tool_calls=None, finish_reason="stop")


class EchoTool(Tool):
    @property
    def name(self):
        return "echo"

    @property
    def description(self):
        return "Echo helper"

    @property
    def parameters(self):
        return {"type": "object", "properties": {"text": {"type": "string"}}}

    async def execute(self, text: str):
        return ToolResult(success=True, content=f"tool:{text}")


class FailingTool(Tool):
    """Returns ToolResult(success=False) rather than raising."""

    @property
    def name(self):
        return "failing"

    @property
    def description(self):
        return "Always fails"

    @property
    def parameters(self):
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs):
        return ToolResult(success=False, content="", error="disk on fire")


class BlankErrorTool(Tool):
    """Fails without populating ``error`` so the default message is used."""

    @property
    def name(self):
        return "blank_error"

    @property
    def description(self):
        return "Fails with no error text"

    @property
    def parameters(self):
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs):
        return ToolResult(success=False, content="", error=None)


class ExceptionTool(Tool):
    """Raises out of ``execute``."""

    @property
    def name(self):
        return "boom"

    @property
    def description(self):
        return "Always raises"

    @property
    def parameters(self):
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs):
        raise ValueError("kaboom")


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def make_tool_call(call_id, name, arguments):
    return ToolCall(id=call_id, type="function", function=FunctionCall(name=name, arguments=arguments))


def make_config(workspace, max_steps=3):
    """Config with workspace-dependent tool loading disabled for isolation."""
    return Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(max_steps=max_steps, workspace_dir=str(workspace)),
        tools=ToolsConfig(enable_file_tools=False, enable_bash=False, enable_note=False, enable_mcp=False),
    )


def build_agent(workspace, llm=None, tools=None, max_steps=3):
    """Construct a MiniMaxACPAgent plus its capture connection."""
    conn = DummyConn()
    adapter = MiniMaxACPAgent(
        conn,
        make_config(workspace, max_steps=max_steps),
        llm if llm is not None else DummyLLM(),
        list(tools) if tools is not None else [EchoTool()],
        "system",
    )
    return adapter, conn


def new_session_params(cwd=None):
    return SimpleNamespace(cwd=cwd)


def prompt_params(session_id, *texts):
    return SimpleNamespace(sessionId=session_id, prompt=[{"text": t} for t in texts])


@pytest.fixture
def acp_agent(tmp_path):
    return build_agent(tmp_path)


# ---------------------------------------------------------------------------
# initialize()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_initialize_returns_protocol_version(acp_agent):
    from acp import PROTOCOL_VERSION

    adapter, _ = acp_agent
    response = await adapter.initialize(SimpleNamespace(protocolVersion=PROTOCOL_VERSION))
    assert response.protocolVersion == PROTOCOL_VERSION


@pytest.mark.asyncio
async def test_initialize_reports_load_session_unsupported(acp_agent):
    adapter, _ = acp_agent
    response = await adapter.initialize(SimpleNamespace(protocolVersion=1))
    assert response.agentCapabilities is not None
    assert response.agentCapabilities.loadSession is False


@pytest.mark.asyncio
async def test_initialize_reports_agent_info(acp_agent):
    adapter, _ = acp_agent
    response = await adapter.initialize(SimpleNamespace(protocolVersion=1))
    assert response.agentInfo is not None
    assert response.agentInfo.name == "mini-agent"
    assert response.agentInfo.title == "Mini-Agent"
    assert response.agentInfo.version == "0.1.0"


# ---------------------------------------------------------------------------
# newSession()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_new_session_uses_absolute_cwd(tmp_path):
    workspace = tmp_path / "elsewhere"
    adapter, _ = build_agent(tmp_path)
    session = await adapter.newSession(new_session_params(cwd=str(workspace)))
    state = adapter._sessions[session.sessionId]
    assert state.agent.workspace_dir == workspace
    assert state.agent.workspace_dir.is_absolute()


@pytest.mark.asyncio
async def test_new_session_resolves_relative_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    adapter, _ = build_agent(tmp_path)
    session = await adapter.newSession(new_session_params(cwd="./nested/ws"))
    state = adapter._sessions[session.sessionId]
    assert state.agent.workspace_dir.is_absolute()
    assert state.agent.workspace_dir == (tmp_path / "nested" / "ws").resolve()


@pytest.mark.asyncio
async def test_new_session_falls_back_to_configured_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    configured = tmp_path / "configured_ws"
    adapter, _ = build_agent(configured)
    session = await adapter.newSession(new_session_params(cwd=None))
    state = adapter._sessions[session.sessionId]
    assert state.agent.workspace_dir == configured


@pytest.mark.asyncio
async def test_new_session_ids_are_unique(acp_agent):
    adapter, _ = acp_agent
    first = await adapter.newSession(new_session_params(cwd=None))
    second = await adapter.newSession(new_session_params(cwd=None))
    assert first.sessionId != second.sessionId
    assert set(adapter._sessions) == {first.sessionId, second.sessionId}


# ---------------------------------------------------------------------------
# prompt() -- happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_acp_turn_executes_tool(acp_agent):
    adapter, conn = acp_agent
    session = await adapter.newSession(new_session_params(cwd=None))
    response = await adapter.prompt(prompt_params(session.sessionId, "hello"))
    assert response.stopReason == "end_turn"
    assert any("tool:ping" in str(update) for update in conn.updates)
    await adapter.cancel(SimpleNamespace(sessionId=session.sessionId))
    assert adapter._sessions[session.sessionId].cancelled


@pytest.mark.asyncio
async def test_prompt_without_tool_calls_ends_turn_and_emits_content(tmp_path):
    llm = ScriptedLLM(LLMResponse(content="hi there", thinking=None, tool_calls=None, finish_reason="stop"))
    adapter, conn = build_agent(tmp_path, llm=llm)
    session = await adapter.newSession(new_session_params(cwd=None))

    response = await adapter.prompt(prompt_params(session.sessionId, "yo"))

    assert response.stopReason == "end_turn"
    assert llm.calls == 1
    messages = conn.of_kind("agent_message_chunk")
    assert [m.update.content.text for m in messages] == ["hi there"]


@pytest.mark.asyncio
async def test_prompt_emits_thinking_as_agent_thought(tmp_path):
    llm = ScriptedLLM(LLMResponse(content="answer", thinking="pondering", tool_calls=None, finish_reason="stop"))
    adapter, conn = build_agent(tmp_path, llm=llm)
    session = await adapter.newSession(new_session_params(cwd=None))

    await adapter.prompt(prompt_params(session.sessionId, "yo"))

    thoughts = conn.of_kind("agent_thought_chunk")
    assert [t.update.content.text for t in thoughts] == ["pondering"]


@pytest.mark.asyncio
async def test_prompt_empty_prompt_is_handled(tmp_path):
    llm = ScriptedLLM(LLMResponse(content="ok", thinking=None, tool_calls=None, finish_reason="stop"))
    adapter, _ = build_agent(tmp_path, llm=llm)
    session = await adapter.newSession(new_session_params(cwd=None))

    response = await adapter.prompt(SimpleNamespace(sessionId=session.sessionId, prompt=[]))

    assert response.stopReason == "end_turn"
    user_messages = [m for m in adapter._sessions[session.sessionId].agent.messages if m.role == "user"]
    assert len(user_messages) == 1
    assert user_messages[0].content == ""


@pytest.mark.asyncio
async def test_prompt_joins_multiple_text_blocks_with_newlines(tmp_path):
    llm = ScriptedLLM(LLMResponse(content="ok", thinking=None, tool_calls=None, finish_reason="stop"))
    adapter, _ = build_agent(tmp_path, llm=llm)
    session = await adapter.newSession(new_session_params(cwd=None))

    await adapter.prompt(prompt_params(session.sessionId, "first", "second", "third"))

    user_messages = [m for m in adapter._sessions[session.sessionId].agent.messages if m.role == "user"]
    assert user_messages[0].content == "first\nsecond\nthird"


@pytest.mark.asyncio
async def test_prompt_accepts_object_style_content_blocks(tmp_path):
    llm = ScriptedLLM(LLMResponse(content="ok", thinking=None, tool_calls=None, finish_reason="stop"))
    adapter, _ = build_agent(tmp_path, llm=llm)
    session = await adapter.newSession(new_session_params(cwd=None))

    params = SimpleNamespace(
        sessionId=session.sessionId,
        prompt=[SimpleNamespace(type="text", text="alpha"), SimpleNamespace(type="text", text="beta")],
    )
    await adapter.prompt(params)

    user_messages = [m for m in adapter._sessions[session.sessionId].agent.messages if m.role == "user"]
    assert user_messages[0].content == "alpha\nbeta"


# ---------------------------------------------------------------------------
# prompt() -- error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prompt_llm_error_returns_refusal_and_reports_error(tmp_path):
    adapter, conn = build_agent(tmp_path, llm=ExplodingLLM("boom-llm"))
    session = await adapter.newSession(new_session_params(cwd=None))

    response = await adapter.prompt(prompt_params(session.sessionId, "hello"))

    assert response.stopReason == "refusal"
    messages = conn.of_kind("agent_message_chunk")
    assert len(messages) == 1
    assert messages[0].update.content.text == "Error: boom-llm"


@pytest.mark.asyncio
async def test_prompt_tool_failure_marks_tool_call_failed(tmp_path):
    llm = ScriptedLLM(
        LLMResponse(content="", thinking=None, tool_calls=[make_tool_call("t1", "failing", {})], finish_reason="tool"),
        LLMResponse(content="recovered", thinking=None, tool_calls=None, finish_reason="stop"),
    )
    adapter, conn = build_agent(tmp_path, llm=llm, tools=[FailingTool()])
    session = await adapter.newSession(new_session_params(cwd=None))

    response = await adapter.prompt(prompt_params(session.sessionId, "go"))

    assert response.stopReason == "end_turn"
    updates = conn.of_kind("tool_call_update")
    assert len(updates) == 1
    assert updates[0].update.status == "failed"
    assert updates[0].update.content[0].content.text == "[ERROR] disk on fire"

    tool_messages = [m for m in adapter._sessions[session.sessionId].agent.messages if m.role == "tool"]
    assert tool_messages[0].content == "[ERROR] disk on fire"


@pytest.mark.asyncio
async def test_prompt_tool_failure_without_error_text_uses_default_message(tmp_path):
    llm = ScriptedLLM(
        LLMResponse(
            content="", thinking=None, tool_calls=[make_tool_call("t1", "blank_error", {})], finish_reason="tool"
        ),
        LLMResponse(content="done", thinking=None, tool_calls=None, finish_reason="stop"),
    )
    adapter, conn = build_agent(tmp_path, llm=llm, tools=[BlankErrorTool()])
    session = await adapter.newSession(new_session_params(cwd=None))

    await adapter.prompt(prompt_params(session.sessionId, "go"))

    updates = conn.of_kind("tool_call_update")
    assert updates[0].update.status == "failed"
    assert updates[0].update.content[0].content.text == "[ERROR] Tool execution failed"


@pytest.mark.asyncio
async def test_prompt_tool_exception_is_caught_and_formatted(tmp_path):
    llm = ScriptedLLM(
        LLMResponse(content="", thinking=None, tool_calls=[make_tool_call("t1", "boom", {})], finish_reason="tool"),
        LLMResponse(content="after", thinking=None, tool_calls=None, finish_reason="stop"),
    )
    adapter, conn = build_agent(tmp_path, llm=llm, tools=[ExceptionTool()])
    session = await adapter.newSession(new_session_params(cwd=None))

    response = await adapter.prompt(prompt_params(session.sessionId, "go"))

    assert response.stopReason == "end_turn"
    updates = conn.of_kind("tool_call_update")
    assert updates[0].update.status == "failed"
    assert updates[0].update.content[0].content.text == "[ERROR] Tool error: kaboom"


@pytest.mark.asyncio
async def test_prompt_unknown_tool_reports_failure(tmp_path):
    llm = ScriptedLLM(
        LLMResponse(content="", thinking=None, tool_calls=[make_tool_call("t1", "nope", {})], finish_reason="tool"),
        LLMResponse(content="after", thinking=None, tool_calls=None, finish_reason="stop"),
    )
    adapter, conn = build_agent(tmp_path, llm=llm, tools=[EchoTool()])
    session = await adapter.newSession(new_session_params(cwd=None))

    response = await adapter.prompt(prompt_params(session.sessionId, "go"))

    assert response.stopReason == "end_turn"
    updates = conn.of_kind("tool_call_update")
    assert updates[0].update.status == "failed"
    assert updates[0].update.content[0].content.text == "[ERROR] Unknown tool: nope"

    tool_messages = [m for m in adapter._sessions[session.sessionId].agent.messages if m.role == "tool"]
    assert tool_messages[0].name == "nope"


# ---------------------------------------------------------------------------
# prompt() -- multi-call and loop control
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prompt_executes_all_tool_calls_in_one_turn(tmp_path):
    calls = [
        make_tool_call("a", "echo", {"text": "one"}),
        make_tool_call("b", "echo", {"text": "two"}),
        make_tool_call("c", "echo", {"text": "three"}),
    ]
    llm = ScriptedLLM(
        LLMResponse(content="", thinking=None, tool_calls=calls, finish_reason="tool"),
        LLMResponse(content="all done", thinking=None, tool_calls=None, finish_reason="stop"),
    )
    adapter, conn = build_agent(tmp_path, llm=llm, tools=[EchoTool()])
    session = await adapter.newSession(new_session_params(cwd=None))

    response = await adapter.prompt(prompt_params(session.sessionId, "go"))

    assert response.stopReason == "end_turn"

    starts = conn.of_kind("tool_call")
    assert [s.update.toolCallId for s in starts] == ["a", "b", "c"]

    updates = conn.of_kind("tool_call_update")
    assert [u.update.toolCallId for u in updates] == ["a", "b", "c"]
    assert all(u.update.status == "completed" for u in updates)
    assert [u.update.content[0].content.text for u in updates] == [
        "[OK] tool:one",
        "[OK] tool:two",
        "[OK] tool:three",
    ]

    tool_messages = [m for m in adapter._sessions[session.sessionId].agent.messages if m.role == "tool"]
    assert [m.tool_call_id for m in tool_messages] == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_prompt_tool_call_start_includes_label_and_raw_input(tmp_path):
    llm = ScriptedLLM(
        LLMResponse(
            content="",
            thinking=None,
            tool_calls=[make_tool_call("a", "echo", {"text": "one"})],
            finish_reason="tool",
        ),
        LLMResponse(content="done", thinking=None, tool_calls=None, finish_reason="stop"),
    )
    adapter, conn = build_agent(tmp_path, llm=llm)
    session = await adapter.newSession(new_session_params(cwd=None))

    await adapter.prompt(prompt_params(session.sessionId, "go"))

    start = conn.of_kind("tool_call")[0].update
    assert start.kind == "execute"
    assert start.rawInput == {"text": "one"}
    assert "echo" in start.title
    assert "text=" in start.title


@pytest.mark.asyncio
async def test_prompt_stops_at_max_steps(tmp_path):
    """An LLM that never stops calling tools must terminate at max_steps."""
    llm = ScriptedLLM(
        LLMResponse(
            content="",
            thinking=None,
            tool_calls=[make_tool_call("loop", "echo", {"text": "again"})],
            finish_reason="tool",
        )
    )
    adapter, _ = build_agent(tmp_path, llm=llm, max_steps=4)
    session = await adapter.newSession(new_session_params(cwd=None))

    response = await adapter.prompt(prompt_params(session.sessionId, "go"))

    assert response.stopReason == "max_turn_requests"
    assert llm.calls == 4


@pytest.mark.asyncio
async def test_prompt_reuses_session_history_across_turns(tmp_path):
    llm = ScriptedLLM(LLMResponse(content="ok", thinking=None, tool_calls=None, finish_reason="stop"))
    adapter, _ = build_agent(tmp_path, llm=llm)
    session = await adapter.newSession(new_session_params(cwd=None))

    await adapter.prompt(prompt_params(session.sessionId, "first"))
    await adapter.prompt(prompt_params(session.sessionId, "second"))

    user_messages = [m for m in adapter._sessions[session.sessionId].agent.messages if m.role == "user"]
    assert [m.content for m in user_messages] == ["first", "second"]


# ---------------------------------------------------------------------------
# cancel()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_mid_turn_stops_next_iteration(tmp_path):
    llm = CancellingLLM()
    adapter, _ = build_agent(tmp_path, llm=llm, max_steps=5)
    session = await adapter.newSession(new_session_params(cwd=None))
    llm.adapter, llm.session_id = adapter, session.sessionId

    response = await adapter.prompt(prompt_params(session.sessionId, "go"))

    assert response.stopReason == "cancelled"
    assert adapter._sessions[session.sessionId].cancelled is True
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_cancel_unknown_session_is_noop(acp_agent):
    adapter, conn = acp_agent
    await adapter.cancel(SimpleNamespace(sessionId="does-not-exist"))
    assert adapter._sessions == {}
    assert conn.updates == []


@pytest.mark.asyncio
async def test_prompt_resets_cancel_flag_from_previous_turn(tmp_path):
    llm = ScriptedLLM(LLMResponse(content="ok", thinking=None, tool_calls=None, finish_reason="stop"))
    adapter, _ = build_agent(tmp_path, llm=llm)
    session = await adapter.newSession(new_session_params(cwd=None))
    await adapter.cancel(SimpleNamespace(sessionId=session.sessionId))
    assert adapter._sessions[session.sessionId].cancelled is True

    response = await adapter.prompt(prompt_params(session.sessionId, "go"))

    assert response.stopReason == "end_turn"
    assert adapter._sessions[session.sessionId].cancelled is False


# ---------------------------------------------------------------------------
# Session auto-creation fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prompt_auto_creates_missing_session(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    workspace = tmp_path / "auto_ws"
    llm = ScriptedLLM(LLMResponse(content="auto ok", thinking=None, tool_calls=None, finish_reason="stop"))
    adapter, conn = build_agent(workspace, llm=llm)

    response = await adapter.prompt(prompt_params("never-created", "hello"))

    assert response.stopReason == "end_turn"
    assert len(adapter._sessions) == 1
    created_id = next(iter(adapter._sessions))
    assert created_id != "never-created"
    assert adapter._sessions[created_id].agent.workspace_dir == Path(workspace).resolve()

    user_messages = [m for m in adapter._sessions[created_id].agent.messages if m.role == "user"]
    assert [m.content for m in user_messages] == ["hello"]
    assert [u.update.content.text for u in conn.of_kind("agent_message_chunk")] == ["auto ok"]


@pytest.mark.asyncio
async def test_prompt_auto_created_session_notifies_requested_session_id(tmp_path, monkeypatch):
    """Updates are addressed to the sessionId the client asked for."""
    monkeypatch.chdir(tmp_path)
    llm = ScriptedLLM(LLMResponse(content="hi", thinking=None, tool_calls=None, finish_reason="stop"))
    adapter, conn = build_agent(tmp_path / "ws", llm=llm)

    await adapter.prompt(prompt_params("client-side-id", "hello"))

    assert conn.updates
    assert all(u.sessionId == "client-side-id" for u in conn.updates)
