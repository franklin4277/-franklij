"""Test cases for streaming support in LLM clients and Agent."""

import asyncio
import inspect
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mini_agent import LLMClient
from mini_agent.agent import Agent
from mini_agent.config import Config
from mini_agent.llm.anthropic_client import AnthropicClient
from mini_agent.llm.base import LLMClientBase
from mini_agent.llm.openai_client import OpenAIClient
from mini_agent.schema import LLMResponse, Message, ToolCall, FunctionCall, TokenUsage


class TestLLMClientStreaming:
    """Test streaming functionality in LLM clients."""

    def test_llm_client_base_has_stream_generate(self):
        """Test that LLMClientBase has stream_generate method."""
        assert hasattr(LLMClientBase, "stream_generate")

    def test_anthropic_client_stream_generate_is_async_generator(self):
        """Test that AnthropicClient.stream_generate is an async generator."""
        client = AnthropicClient(
            api_key="test-key",
            api_base="https://api.minimaxi.com/anthropic",
            model="MiniMax-M2.5",
        )
        assert hasattr(client, "stream_generate")
        assert inspect.isasyncgenfunction(client.stream_generate)

    def test_openai_client_stream_generate_is_async_generator(self):
        """Test that OpenAIClient.stream_generate is an async generator."""
        client = OpenAIClient(
            api_key="test-key",
            api_base="https://api.minimaxi.com/v1",
            model="MiniMax-M2.5",
        )
        assert hasattr(client, "stream_generate")
        assert inspect.isasyncgenfunction(client.stream_generate)


class TestStreamingResponseAccumulation:
    """Test that streaming responses accumulate content correctly."""

    @pytest.mark.asyncio
    async def test_streaming_returns_async_generator_type(self):
        """Test that stream_generate returns an async generator."""
        client = AnthropicClient(
            api_key="test-key",
            api_base="https://api.minimaxi.com/anthropic",
            model="MiniMax-M2.5",
        )

        messages = [Message(role="user", content="Test")]

        with patch.object(client.client.messages, "stream") as mock_stream:
            mock_stream.return_value.__aenter__ = AsyncMock()
            mock_stream.return_value.__aexit__ = AsyncMock()
            mock_stream.return_value.__anext__ = AsyncMock(
                side_effect=StopAsyncIteration
            )

            result = client.stream_generate(messages=messages)
            assert inspect.isasyncgen(result)


class TestAgentStreaming:
    """Test Agent streaming functionality."""

    def test_agent_has_enable_streaming_parameter(self):
        """Test that Agent.__init__ accepts enable_streaming parameter."""
        sig = inspect.signature(Agent.__init__)
        params = list(sig.parameters.keys())
        assert "enable_streaming" in params

    @pytest.mark.asyncio
    async def test_agent_without_streaming_uses_generate(self):
        """Test that Agent without streaming uses regular generate()."""
        llm_client = MagicMock()
        llm_client.generate = AsyncMock(
            return_value=LLMResponse(
                content="Test response",
                finish_reason="stop",
            )
        )

        agent = Agent(
            llm_client=llm_client,
            system_prompt="You are helpful.",
            tools=[],
            max_steps=1,
            enable_streaming=False,
        )

        agent.add_user_message("Hello")
        result = await agent.run()

        llm_client.generate.assert_called_once()
        assert "Test response" in result

    @pytest.mark.asyncio
    async def test_agent_with_streaming_uses_stream_generate(self):
        """Test that Agent with streaming uses stream_generate()."""
        llm_client = MagicMock()

        mock_stream_gen = MagicMock()

        async def mock_stream_generate(*args, **kwargs):
            yield LLMResponse(content="Hello ", finish_reason="", usage=None)
            yield LLMResponse(content="Hello world!", finish_reason="stop", usage=None)

        mock_stream_gen.side_effect = mock_stream_generate
        llm_client.stream_generate = mock_stream_gen

        agent = Agent(
            llm_client=llm_client,
            system_prompt="You are helpful.",
            tools=[],
            max_steps=1,
            enable_streaming=True,
        )

        agent.add_user_message("Say hello")
        result = await agent.run()

        llm_client.stream_generate.assert_called_once()
        assert "Hello world!" in result

    @pytest.mark.asyncio
    async def test_agent_streaming_default_is_false(self):
        """Test that Agent.enable_streaming defaults to False."""
        llm_client = MagicMock()
        llm_client.generate = AsyncMock(
            return_value=LLMResponse(
                content="Test",
                finish_reason="stop",
            )
        )

        agent = Agent(
            llm_client=llm_client,
            system_prompt="You are helpful.",
            tools=[],
            max_steps=1,
        )

        assert agent.enable_streaming is False


class TestStreamingConfig:
    """Test streaming configuration."""

    def test_llm_config_has_enable_streaming_field(self):
        """Test that LLMConfig has enable_streaming field."""
        from mini_agent.config import LLMConfig

        fields = LLMConfig.model_fields
        assert "enable_streaming" in fields

    def test_llm_config_enable_streaming_defaults_to_false(self):
        """Test that enable_streaming defaults to False."""
        from mini_agent.config import LLMConfig

        config = LLMConfig(api_key="test-key")
        assert config.enable_streaming is False

    def test_llm_config_enable_streaming_can_be_set_true(self):
        """Test that enable_streaming can be set to True."""
        from mini_agent.config import LLMConfig

        config = LLMConfig(api_key="test-key", enable_streaming=True)
        assert config.enable_streaming is True


class TestStreamingMethodSignatures:
    """Test streaming method signatures are correct."""

    def test_stream_generate_has_correct_signature_anthropic(self):
        """Test AnthropicClient.stream_generate has correct signature."""
        sig = inspect.signature(AnthropicClient.stream_generate)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "messages" in params
        assert "tools" in params

    def test_stream_generate_has_correct_signature_openai(self):
        """Test OpenAIClient.stream_generate has correct signature."""
        sig = inspect.signature(OpenAIClient.stream_generate)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "messages" in params
        assert "tools" in params


class TestStreamingEdgeCases:
    """Test streaming edge cases."""

    @pytest.mark.asyncio
    async def test_streaming_with_no_tools(self):
        """Test streaming works with no tools provided."""
        client = AnthropicClient(
            api_key="test-key",
            api_base="https://api.minimaxi.com/anthropic",
            model="MiniMax-M2.5",
        )

        messages = [Message(role="user", content="Hello")]

        with patch.object(client.client.messages, "stream") as mock_stream:
            mock_stream.return_value.__aenter__ = AsyncMock()
            mock_stream.return_value.__aexit__ = AsyncMock()

            async def fake_iter():
                yield

            mock_stream.return_value.__anext__ = fake_iter().__anext__

            result = client.stream_generate(messages=messages)
            assert inspect.isasyncgen(result)

    @pytest.mark.asyncio
    async def test_agent_handles_streaming_empty_response(self):
        """Test Agent handles empty streaming response."""
        llm_client = MagicMock()

        async def mock_stream_generate(*args, **kwargs):
            yield LLMResponse(content="", finish_reason="stop", usage=None)

        llm_client.stream_generate = mock_stream_generate

        agent = Agent(
            llm_client=llm_client,
            system_prompt="You are helpful.",
            tools=[],
            max_steps=1,
            enable_streaming=True,
        )

        agent.add_user_message("Empty response")
        result = await agent.run()
        assert result == ""

    @pytest.mark.asyncio
    async def test_agent_streaming_with_single_yield(self):
        """Test Agent with streaming that yields only once."""
        llm_client = MagicMock()

        async def mock_stream_generate(*args, **kwargs):
            yield LLMResponse(
                content="Single response!", finish_reason="stop", usage=None
            )

        llm_client.stream_generate = mock_stream_generate

        agent = Agent(
            llm_client=llm_client,
            system_prompt="You are helpful.",
            tools=[],
            max_steps=1,
            enable_streaming=True,
        )

        agent.add_user_message("Say something")
        result = await agent.run()
        assert "Single response!" in result


async def main():
    """Run all streaming tests."""
    print("=" * 80)
    print("Running Streaming Support Tests")
    print("=" * 80)

    tests = [
        TestLLMClientStreaming(),
        TestStreamingResponseAccumulation(),
        TestAgentStreaming(),
        TestStreamingConfig(),
        TestStreamingMethodSignatures(),
        TestStreamingEdgeCases(),
    ]

    total = 0
    passed = 0

    for test_class in tests:
        print(f"\n{test_class.__name__}")
        print("-" * 40)
        for name in dir(test_class):
            if name.startswith("test_"):
                total += 1
                try:
                    test_method = getattr(test_class, name)
                    if asyncio.iscoroutinefunction(test_method):
                        await test_method()
                    else:
                        test_method()
                    print(f"  ✅ {name}")
                    passed += 1
                except Exception as e:
                    print(f"  ❌ {name}: {e}")

    print("\n" + "=" * 80)
    print(f"Results: {passed}/{total} tests passed")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
