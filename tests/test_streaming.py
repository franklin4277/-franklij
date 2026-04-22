"""Tests for Agent.run_streaming()."""

import asyncio
import pytest

from mini_agent.agent import Agent
from mini_agent.schema import AgentEvent, Message


class MockLLMClient:
    """Minimal mock LLM client for testing."""

    def __init__(self, response_content: str = "Test response", tool_calls: list | None = None):
        self.response_content = response_content
        self.tool_calls = tool_calls or []
        self.call_count = 0

    async def generate(self, messages: list[Message], tools: list | None = None):
        self.call_count += 1
        from mini_agent.schema import LLMResponse, TokenUsage

        class FakeResponse:
            content = self.response_content
            thinking = None
            tool_calls = self.tool_calls if self.call_count == 1 else None
            finish_reason = "tool_use" if self.tool_calls and self.call_count == 1 else "stop"
            usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)

        return FakeResponse()


@pytest.mark.asyncio
async def test_run_streaming_yields_content_event():
    """run_streaming() yields content event when LLM returns text."""
    agent = Agent(
        llm_client=MockLLMClient(response_content="Hello world"),
        system_prompt="You are a helpful assistant.",
        tools=[],
        max_steps=5,
    )
    agent.add_user_message("Say hello")

    events = [e async for e in agent.run_streaming()]

    assert len(events) >= 1
    assert events[0].type == "content"
    assert events[0].content == "Hello world"
    assert events[-1].type == "final"
    assert events[-1].final_text == "Hello world"


@pytest.mark.asyncio
async def test_run_streaming_yields_final_event():
    """run_streaming() always ends with a final event."""
    agent = Agent(
        llm_client=MockLLMClient(response_content="Done"),
        system_prompt="You are a helpful assistant.",
        tools=[],
        max_steps=5,
    )
    agent.add_user_message("End the conversation")

    events = [e async for e in agent.run_streaming()]

    assert any(e.type == "final" for e in events)
    final_event = next(e for e in events if e.type == "final")
    assert final_event.final_text == "Done"
    assert final_event.total_tokens == 150


@pytest.mark.asyncio
async def test_run_streaming_event_types():
    """run_streaming() yields correct event types in order."""
    from mini_agent.schema import FunctionCall, ToolCall

    tool_calls = [
        ToolCall(
            id="call_1",
            type="function",
            function=FunctionCall(name="get_weather", arguments={"city": "Beijing"}),
        )
    ]

    agent = Agent(
        llm_client=MockLLMClient(response_content="Let me check the weather.", tool_calls=tool_calls),
        system_prompt="You are a helpful assistant.",
        tools=[],
        max_steps=5,
    )
    agent.add_user_message("What's the weather in Beijing?")

    events = [e async for e in agent.run_streaming()]

    event_types = [e.type for e in events]

    # First: content from first LLM response
    assert "content" in event_types
    # Then: tool_call
    assert "tool_call" in event_types
    # Then: tool_result (from the mock tool)
    assert "tool_result" in event_types
    # Then: step_complete
    assert "step_complete" in event_types
    # Finally: final
    assert "final" in event_types

    # Verify ordering
    content_idx = event_types.index("content")
    tool_call_idx = event_types.index("tool_call")
    tool_result_idx = event_types.index("tool_result")
    step_complete_idx = event_types.index("step_complete")

    assert content_idx < tool_call_idx < tool_result_idx < step_complete_idx


@pytest.mark.asyncio
async def test_run_streaming_tool_call_event():
    """run_streaming() includes correct tool_call info in event."""
    from mini_agent.schema import FunctionCall, ToolCall

    tool_calls = [
        ToolCall(
            id="call_abc",
            type="function",
            function=FunctionCall(name="get_stock_price", arguments={"symbol": "AAPL"}),
        )
    ]

    agent = Agent(
        llm_client=MockLLMClient(response_content="Getting stock price.", tool_calls=tool_calls),
        system_prompt="You are a helpful assistant.",
        tools=[],
        max_steps=5,
    )
    agent.add_user_message("Get AAPL price")

    events = [e async for e in agent.run_streaming()]

    tool_call_event = next(e for e in events if e.type == "tool_call")
    assert tool_call_event.tool_call.id == "call_abc"
    assert tool_call_event.tool_call.name == "get_stock_price"
    assert tool_call_event.tool_call.arguments == {"symbol": "AAPL"}


@pytest.mark.asyncio
async def test_run_streaming_unknown_tool_yields_error_result():
    """run_streaming() handles unknown tools gracefully."""
    from mini_agent.schema import FunctionCall, ToolCall

    tool_calls = [
        ToolCall(
            id="call_xyz",
            type="function",
            function=FunctionCall(name="nonexistent_tool", arguments={}),
        )
    ]

    agent = Agent(
        llm_client=MockLLMClient(response_content="Calling unknown tool.", tool_calls=tool_calls),
        system_prompt="You are a helpful assistant.",
        tools=[],  # No tools registered
        max_steps=5,
    )
    agent.add_user_message("Use a tool that doesn't exist")

    events = [e async for e in agent.run_streaming()]

    tool_result_event = next(e for e in events if e.type == "tool_result")
    assert tool_result_event.tool_result.success is False
    assert "Unknown tool" in tool_result_event.tool_result.error


@pytest.mark.asyncio
async def test_run_streaming_cancel_via_event():
    """run_streaming() respects cancel_event to interrupt execution."""
    agent = Agent(
        llm_client=MockLLMClient(response_content="Should not reach here"),
        system_prompt="You are a helpful assistant.",
        tools=[],
        max_steps=5,
    )
    agent.add_user_message("Long task")

    cancel_event = asyncio.Event()
    cancel_event.set()  # Cancel immediately

    events = [e async for e in agent.run_streaming(cancel_event=cancel_event)]

    assert any(e.type == "final" for e in events)
    final_event = next(e for e in events if e.type == "final")
    assert "cancelled" in final_event.final_text.lower()


@pytest.mark.asyncio
async def test_run_streaming_max_steps_yields_final():
    """run_streaming() yields final with max steps message when limit reached."""
    from mini_agent.schema import FunctionCall, ToolCall

    # Infinite loop: LLM always requests the same tool
    tool_calls = [
        ToolCall(
            id="call_loop",
            type="function",
            function=FunctionCall(name="dummy_tool", arguments={}),
        )
    ]

    class LoopingLLM(MockLLMClient):
        async def generate(self, messages, tools=None):
            self.call_count += 1
            from mini_agent.schema import LLMResponse, TokenUsage

            class FakeResponse:
                content = f"Step {self.call_count}"
                thinking = None
                tool_calls = tool_calls if self.call_count <= 3 else None
                finish_reason = "tool_use"
                usage = TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)

            return FakeResponse()

    agent = Agent(
        llm_client=LoopingLLM(),
        system_prompt="You are a helpful assistant.",
        tools=[],  # No actual tools - will get "unknown tool" but loop continues
        max_steps=3,
    )
    agent.add_user_message("Keep calling tools forever")

    events = [e async for e in agent.run_streaming()]

    final_event = next(e for e in events if e.type == "final")
    assert "couldn't be completed" in final_event.final_text.lower()
