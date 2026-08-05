"""Unit tests for AnthropicClient and OpenAIClient internal methods.

These tests are fully mocked — they do not require live API keys or network access.
They cover:
  - _convert_messages: system extraction, role preservation, tool result wrapping,
    assistant thinking/tool_calls content blocks (Anthropic) and reasoning_details (OpenAI).
  - _convert_tools: dict passthrough / OpenAI format passthrough / conversion from
    Anthropic-shaped dict to OpenAI-shaped dict.
  - _prepare_request: the dict shape produced for splatting into _make_api_request.
  - _parse_response: extraction of content, thinking, tool calls, and token usage
    from provider-shaped response stubs.
  - _request_with_retry: verified retry path on transient errors and exhaustion
    after max_retries.

No live API calls. No try/except Exception swallowing.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mini_agent.llm import AnthropicClient, OpenAIClient
from mini_agent.logger import RetryConfig, RetryExhaustedError
from mini_agent.schema import FunctionCall, Message, TokenUsage, ToolCall


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def anthropic_client() -> AnthropicClient:
    """An AnthropicClient that bypasses the real SDK constructor.

    The real ``__init__`` instantiates ``anthropic.AsyncAnthropic`` which would try
    to talk to the network. We monkey-patch the SDK import target to a MagicMock
    so that init is hermetic.
    """
    with patch("mini_agent.llm.anthropic_client.anthropic") as mock_anthropic_module:
        mock_anthropic_module.AsyncAnthropic.return_value = MagicMock()
        client = AnthropicClient(api_key="test-key")
    # Force no real network: zero the inner SDK handle explicitly.
    client.client = MagicMock()
    return client


@pytest.fixture
def openai_client() -> OpenAIClient:
    """An OpenAIClient constructed without touching the real SDK.

    ``AsyncOpenAI`` from the openai SDK does not make network calls in its
    ``__init__``, but we still patch it for symmetry and to avoid surprises if
    the SDK starts doing lazy validation.
    """
    with patch("mini_agent.llm.openai_client.AsyncOpenAI") as mock_async_openai:
        mock_async_openai.return_value = MagicMock()
        client = OpenAIClient(api_key="test-key")
    client.client = MagicMock()
    return client


def _make_anthropic_tool_call_block(block_id: str = "tu_1", name: str = "get_weather", input: dict | None = None):
    """Build an ``anthropic``-style content block stub for ``tool_use``."""
    block = MagicMock()
    block.type = "tool_use"
    block.id = block_id
    block.name = name
    block.input = input if input is not None else {"location": "SF"}
    return block


def _make_anthropic_text_block(text: str):
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _make_anthropic_thinking_block(thinking: str):
    block = MagicMock()
    block.type = "thinking"
    block.thinking = thinking
    return block


def _build_anthropic_response(
    blocks: list[Any],
    stop_reason: str | None = "end_turn",
    usage_kwargs: dict[str, Any] | None = None,
):
    """Build a stub that mimics ``anthropic.types.Message`` for ``_parse_response``."""
    response = MagicMock()
    response.content = blocks
    response.stop_reason = stop_reason
    if usage_kwargs is None:
        usage_kwargs = {"input_tokens": 10, "output_tokens": 20, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    usage = MagicMock()
    usage.input_tokens = usage_kwargs.get("input_tokens")
    usage.output_tokens = usage_kwargs.get("output_tokens")
    usage.cache_read_input_tokens = usage_kwargs.get("cache_read_input_tokens", 0)
    usage.cache_creation_input_tokens = usage_kwargs.get("cache_creation_input_tokens", 0)
    response.usage = usage
    return response


def _build_openai_response(
    content: str = "",
    tool_calls: list[Any] | None = None,
    reasoning_details: list[Any] | None = None,
    usage_kwargs: dict[str, Any] | None = None,
):
    """Build a stub that mimics an OpenAI ChatCompletion response."""
    message = MagicMock()
    message.content = content
    message.tool_calls = tool_calls
    message.reasoning_details = reasoning_details

    choice = MagicMock()
    choice.message = message

    response = MagicMock()
    response.choices = [choice]

    usage = MagicMock()
    if usage_kwargs is None:
        usage_kwargs = {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
    usage.prompt_tokens = usage_kwargs.get("prompt_tokens")
    usage.completion_tokens = usage_kwargs.get("completion_tokens")
    usage.total_tokens = usage_kwargs.get("total_tokens")
    response.usage = usage
    return response


def _make_openai_tool_call(call_id: str = "call_1", name: str = "get_weather", arguments_json: str = '{"location": "SF"}'):
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = arguments_json
    return tc


def _make_openai_reasoning_detail(text: str):
    d = MagicMock()
    d.text = text
    return d


# =============================================================================
# AnthropicClient._convert_messages
# =============================================================================


class TestAnthropicConvertMessages:
    def test_extracts_single_system_message_and_returns_none_when_absent(self, anthropic_client):
        messages = [
            Message(role="system", content="You are helpful."),
            Message(role="user", content="Hi"),
        ]
        system_msg, api_messages = anthropic_client._convert_messages(messages)
        assert system_msg == "You are helpful."
        assert api_messages == [{"role": "user", "content": "Hi"}]

    def test_keeps_last_system_message_when_multiple_present(self, anthropic_client):
        # The implementation keeps overwriting; last write wins. This pins behavior.
        messages = [
            Message(role="system", content="first system"),
            Message(role="user", content="hello"),
            Message(role="system", content="second system"),
        ]
        system_msg, api_messages = anthropic_client._convert_messages(messages)
        assert system_msg == "second system"
        assert api_messages == [{"role": "user", "content": "hello"}]

    def test_user_and_assistant_roles_preserved_with_simple_string_content(self, anthropic_client):
        messages = [
            Message(role="user", content="What is 2+2?"),
            Message(role="assistant", content="4"),
        ]
        _, api_messages = anthropic_client._convert_messages(messages)
        assert api_messages == [
            {"role": "user", "content": "What is 2+2?"},
            {"role": "assistant", "content": "4"},
        ]

    def test_assistant_with_tool_calls_becomes_content_blocks(self, anthropic_client):
        messages = [
            Message(
                role="assistant",
                content="",
                tool_calls=[
                    ToolCall(
                        id="tc_42",
                        type="function",
                        function=FunctionCall(name="get_weather", arguments={"location": "SF"}),
                    )
                ],
            )
        ]
        _, api_messages = anthropic_client._convert_messages(messages)
        assert len(api_messages) == 1
        assistant_block = api_messages[0]
        assert assistant_block["role"] == "assistant"
        assert isinstance(assistant_block["content"], list)
        # tool_use content block was emitted
        tool_blocks = [b for b in assistant_block["content"] if b["type"] == "tool_use"]
        assert tool_blocks == [
            {"type": "tool_use", "id": "tc_42", "name": "get_weather", "input": {"location": "SF"}}
        ]

    def test_assistant_with_thinking_and_text_emits_thinking_then_text_blocks(self, anthropic_client):
        messages = [
            Message(role="assistant", content="Answer is 4.", thinking="Let me think...")
        ]
        _, api_messages = anthropic_client._convert_messages(messages)
        assert len(api_messages) == 1
        content = api_messages[0]["content"]
        assert content[0] == {"type": "thinking", "thinking": "Let me think..."}
        assert content[1] == {"type": "text", "text": "Answer is 4."}

    def test_tool_role_message_wrapped_as_user_with_tool_result_block(self, anthropic_client):
        messages = [
            Message(role="tool", tool_call_id="tc_42", content="72 degrees")
        ]
        _, api_messages = anthropic_client._convert_messages(messages)
        assert api_messages == [
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "tc_42", "content": "72 degrees"}
                ],
            }
        ]


# =============================================================================
# OpenAIClient._convert_messages
# =============================================================================


class TestOpenAIConvertMessages:
    def test_system_message_kept_in_messages_array_and_tuple_system_is_none(self, openai_client):
        messages = [
            Message(role="system", content="You are helpful."),
            Message(role="user", content="Hi"),
        ]
        system_msg, api_messages = openai_client._convert_messages(messages)
        assert system_msg is None
        assert api_messages == [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hi"},
        ]

    def test_user_message_passes_through_unchanged(self, openai_client):
        messages = [Message(role="user", content="Tell me a joke.")]
        _, api_messages = openai_client._convert_messages(messages)
        assert api_messages == [{"role": "user", "content": "Tell me a joke."}]

    def test_assistant_with_tool_calls_serializes_arguments_as_json(self, openai_client):
        messages = [
            Message(
                role="assistant",
                content="",
                tool_calls=[
                    ToolCall(
                        id="call_1",
                        type="function",
                        function=FunctionCall(name="get_weather", arguments={"location": "SF"}),
                    )
                ],
            )
        ]
        _, api_messages = openai_client._convert_messages(messages)
        assert len(api_messages) == 1
        assistant_msg = api_messages[0]
        assert assistant_msg["role"] == "assistant"
        assert "tool_calls" in assistant_msg
        assert assistant_msg["tool_calls"] == [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "arguments": '{"location": "SF"}',
                },
            }
        ]

    def test_assistant_with_thinking_emits_reasoning_details(self, openai_client):
        messages = [
            Message(role="assistant", content="42", thinking="Reasoning about it...")
        ]
        _, api_messages = openai_client._convert_messages(messages)
        assert api_messages[0]["content"] == "42"
        assert api_messages[0]["reasoning_details"] == [{"text": "Reasoning about it..."}]

    def test_tool_role_message_uses_native_tool_role_with_tool_call_id(self, openai_client):
        messages = [Message(role="tool", tool_call_id="call_1", content="result content")]
        _, api_messages = openai_client._convert_messages(messages)
        assert api_messages == [
            {"role": "tool", "tool_call_id": "call_1", "content": "result content"}
        ]


# =============================================================================
# AnthropicClient._convert_tools
# =============================================================================


class TestAnthropicConvertTools:
    def test_dicts_passed_through_unchanged(self, anthropic_client):
        tool = {
            "name": "get_weather",
            "description": "Get the weather",
            "input_schema": {"type": "object", "properties": {"location": {"type": "string"}}},
        }
        assert anthropic_client._convert_tools([tool]) == [tool]

    def test_object_with_to_schema_is_converted(self, anthropic_client):
        class FakeTool:
            def to_schema(self):
                return {
                    "name": "calc",
                    "description": "calculator",
                    "input_schema": {"type": "object"},
                }

        result = anthropic_client._convert_tools([FakeTool()])
        assert result == [
            {"name": "calc", "description": "calculator", "input_schema": {"type": "object"}}
        ]

    def test_unsupported_type_raises_typeerror(self, anthropic_client):
        with pytest.raises(TypeError, match="Unsupported tool type"):
            anthropic_client._convert_tools([42])

    def test_mixed_list_of_dict_and_schema_object(self, anthropic_client):
        class FakeTool:
            def to_schema(self):
                return {"name": "b", "description": "B", "input_schema": {"type": "object"}}

        tool_dict = {"name": "a", "description": "A", "input_schema": {"type": "object"}}
        result = anthropic_client._convert_tools([tool_dict, FakeTool()])
        assert result[0] == tool_dict
        assert result[1] == {"name": "b", "description": "B", "input_schema": {"type": "object"}}


# =============================================================================
# OpenAIClient._convert_tools
# =============================================================================


class TestOpenAIConvertTools:
    def test_openai_shaped_dict_passed_through_unchanged(self, openai_client):
        oai_tool = {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get weather",
                "parameters": {"type": "object"},
            },
        }
        assert openai_client._convert_tools([oai_tool]) == [oai_tool]

    def test_anthropic_shaped_dict_converted_to_openai_shape(self, openai_client):
        anthropic_tool = {
            "name": "get_weather",
            "description": "Get the weather",
            "input_schema": {"type": "object", "properties": {"location": {"type": "string"}}},
        }
        result = openai_client._convert_tools([anthropic_tool])
        assert result == [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get the weather",
                    "parameters": {"type": "object", "properties": {"location": {"type": "string"}}},
                },
            }
        ]

    def test_object_with_to_openai_schema_is_used(self, openai_client):
        class FakeTool:
            def to_openai_schema(self):
                return {"type": "function", "function": {"name": "x", "parameters": {}}}

        result = openai_client._convert_tools([FakeTool()])
        assert result == [{"type": "function", "function": {"name": "x", "parameters": {}}}]

    def test_unsupported_type_raises_typeerror(self, openai_client):
        with pytest.raises(TypeError, match="Unsupported tool type"):
            openai_client._convert_tools([3.14])


# =============================================================================
# AnthropicClient._prepare_request
# =============================================================================


class TestAnthropicPrepareRequest:
    def test_returns_dict_with_system_message_and_api_messages(self, anthropic_client):
        messages = [
            Message(role="system", content="be brief"),
            Message(role="user", content="hi"),
            Message(role="assistant", content="hello"),
        ]
        result = anthropic_client._prepare_request(messages)
        assert result["system_message"] == "be brief"
        assert result["api_messages"] == [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        # No tools passed -> tools is None in the request dict
        assert result["tools"] is None

    def test_tools_field_is_passthrough_not_converted(self, anthropic_client):
        # _prepare_request does not call _convert_tools; tools are forwarded as-is
        # and the conversion happens inside _make_api_request. Pin that contract.
        tool = {"name": "x", "description": "x", "input_schema": {"type": "object"}}
        messages = [Message(role="user", content="hi")]
        result = anthropic_client._prepare_request(messages, tools=[tool])
        assert result["tools"] == [tool]

    def test_keys_match_make_api_request_parameters(self, anthropic_client):
        # The dict from _prepare_request is splatted into _make_api_request, so the
        # keys must be exactly those accepted by _make_api_request.
        import inspect

        sig = inspect.signature(anthropic_client._make_api_request)
        expected_keys = set(sig.parameters.keys())
        result = anthropic_client._prepare_request([Message(role="user", content="x")])
        assert set(result.keys()) == expected_keys


# =============================================================================
# OpenAIClient._prepare_request
# =============================================================================


class TestOpenAIPrepareRequest:
    def test_returns_dict_with_api_messages_only_no_system_key(self, openai_client):
        messages = [
            Message(role="system", content="be brief"),
            Message(role="user", content="hi"),
        ]
        result = openai_client._prepare_request(messages)
        # OpenAI keeps system inline in messages; the splat returns no system_message.
        assert "system_message" not in result
        assert result["api_messages"] == [
            {"role": "system", "content": "be brief"},
            {"role": "user", "content": "hi"},
        ]
        assert result["tools"] is None

    def test_tools_field_is_passthrough_not_converted(self, openai_client):
        tool = {"type": "function", "function": {"name": "x", "parameters": {}}}
        messages = [Message(role="user", content="hi")]
        result = openai_client._prepare_request(messages, tools=[tool])
        assert result["tools"] == [tool]

    def test_keys_match_make_api_request_parameters(self, openai_client):
        # The dict keys must match _make_api_request's named parameters exactly.
        import inspect

        sig = inspect.signature(openai_client._make_api_request)
        expected_keys = set(sig.parameters.keys())
        result = openai_client._prepare_request([Message(role="user", content="x")])
        assert set(result.keys()) == expected_keys


# =============================================================================
# AnthropicClient._parse_response
# =============================================================================


class TestAnthropicParseResponse:
    def test_text_block_extracted_into_content(self, anthropic_client):
        response = _build_anthropic_response([_make_anthropic_text_block("Hello, world")])
        parsed = anthropic_client._parse_response(response)
        assert parsed.content == "Hello, world"
        assert parsed.thinking is None
        assert parsed.tool_calls is None
        assert parsed.finish_reason == "end_turn"

    def test_thinking_block_extracted_into_thinking_field(self, anthropic_client):
        response = _build_anthropic_response(
            [
                _make_anthropic_thinking_block("reasoning here"),
                _make_anthropic_text_block("answer"),
            ]
        )
        parsed = anthropic_client._parse_response(response)
        assert parsed.thinking == "reasoning here"
        assert parsed.content == "answer"

    def test_tool_use_block_parsed_into_tool_calls(self, anthropic_client):
        response = _build_anthropic_response(
            [
                _make_anthropic_text_block(""),
                _make_anthropic_tool_call_block(block_id="tu_99", name="calc", input={"x": 1}),
            ]
        )
        parsed = anthropic_client._parse_response(response)
        assert parsed.tool_calls is not None
        assert len(parsed.tool_calls) == 1
        tc = parsed.tool_calls[0]
        assert tc.id == "tu_99"
        assert tc.type == "function"
        assert tc.function.name == "calc"
        assert tc.function.arguments == {"x": 1}

    def test_token_usage_aggregates_cache_tokens_into_prompt_tokens(self, anthropic_client):
        response = _build_anthropic_response(
            [_make_anthropic_text_block("ok")],
            usage_kwargs={
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_read_input_tokens": 30,
                "cache_creation_input_tokens": 20,
            },
        )
        parsed = anthropic_client._parse_response(response)
        assert isinstance(parsed.usage, TokenUsage)
        # prompt_tokens == input + cache_read + cache_creation
        assert parsed.usage.prompt_tokens == 150
        assert parsed.usage.completion_tokens == 50
        assert parsed.usage.total_tokens == 200

    def test_finish_reason_defaults_to_stop_when_none(self, anthropic_client):
        response = _build_anthropic_response([_make_anthropic_text_block("ok")], stop_reason=None)
        parsed = anthropic_client._parse_response(response)
        assert parsed.finish_reason == "stop"

    def test_missing_usage_attribute_does_not_crash(self, anthropic_client):
        response = MagicMock()
        response.content = [_make_anthropic_text_block("hi")]
        response.stop_reason = "end_turn"
        # No usage attribute
        del response.usage
        parsed = anthropic_client._parse_response(response)
        assert parsed.content == "hi"
        assert parsed.usage is None


# =============================================================================
# OpenAIClient._parse_response
# =============================================================================


class TestOpenAIParseResponse:
    def test_content_extracted(self, openai_client):
        response = _build_openai_response(content="Hello from OpenAI")
        parsed = openai_client._parse_response(response)
        assert parsed.content == "Hello from OpenAI"
        assert parsed.thinking is None
        assert parsed.tool_calls is None

    def test_reasoning_details_extracted_into_thinking(self, openai_client):
        response = _build_openai_response(
            content="Final answer",
            reasoning_details=[_make_openai_reasoning_detail("chain of thought line 1")],
        )
        parsed = openai_client._parse_response(response)
        assert parsed.content == "Final answer"
        assert parsed.thinking == "chain of thought line 1"

    def test_tool_calls_parsed_with_json_arguments(self, openai_client):
        response = _build_openai_response(
            content="",
            tool_calls=[
                _make_openai_tool_call(
                    call_id="call_xyz",
                    name="calc",
                    arguments_json='{"x": 5, "y": 7}',
                )
            ],
        )
        parsed = openai_client._parse_response(response)
        assert parsed.tool_calls is not None
        assert len(parsed.tool_calls) == 1
        tc = parsed.tool_calls[0]
        assert tc.id == "call_xyz"
        assert tc.type == "function"
        assert tc.function.name == "calc"
        # arguments should be parsed back to dict, not remain a string
        assert tc.function.arguments == {"x": 5, "y": 7}

    def test_token_usage_propagated_verbatim(self, openai_client):
        response = _build_openai_response(
            content="ok",
            usage_kwargs={"prompt_tokens": 7, "completion_tokens": 11, "total_tokens": 18},
        )
        parsed = openai_client._parse_response(response)
        assert isinstance(parsed.usage, TokenUsage)
        assert parsed.usage.prompt_tokens == 7
        assert parsed.usage.completion_tokens == 11
        assert parsed.usage.total_tokens == 18

    def test_finish_reason_always_stop_for_openai(self, openai_client):
        response = _build_openai_response(content="ok")
        parsed = openai_client._parse_response(response)
        # OpenAI client hardcodes finish_reason to "stop"
        assert parsed.finish_reason == "stop"

    def test_missing_usage_attribute_does_not_crash(self, openai_client):
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = "hi"
        response.choices[0].message.tool_calls = None
        response.choices[0].message.reasoning_details = None
        del response.usage
        parsed = openai_client._parse_response(response)
        assert parsed.content == "hi"
        assert parsed.usage is None


# =============================================================================
# Retry logic in _request_with_retry (shared by both clients)
# =============================================================================


class TestRequestWithRetry:
    """The retry contract lives on the base class, but the per-client
    ``_make_api_request`` signatures differ. We exercise both branches to lock in
    the retry behavior for each."""

    @pytest.mark.asyncio
    async def test_succeeds_on_first_attempt_without_retrying(self, anthropic_client):
        anthropic_client.retry_config = RetryConfig(enabled=True, max_retries=3)
        anthropic_client._make_api_request = AsyncMock(return_value="SUCCESS")
        result = await anthropic_client._request_with_retry(
            {"system_message": None, "api_messages": [], "tools": None}
        )
        assert result == "SUCCESS"
        assert anthropic_client._make_api_request.await_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_transient_error_then_succeeds(self, anthropic_client):
        # Two failures then success.
        anthropic_client.retry_config = RetryConfig(
            enabled=True, max_retries=3, initial_delay=0.0
        )
        anthropic_client._make_api_request = AsyncMock(
            side_effect=[ConnectionError("boom"), ConnectionError("boom again"), "RECOVERED"]
        )
        result = await anthropic_client._request_with_retry(
            {"system_message": None, "api_messages": [], "tools": None}
        )
        assert result == "RECOVERED"
        assert anthropic_client._make_api_request.await_count == 3

    @pytest.mark.asyncio
    async def test_raises_retry_exhausted_after_max_retries(self, anthropic_client):
        anthropic_client.retry_config = RetryConfig(enabled=True, max_retries=2, initial_delay=0.0)
        anthropic_client._make_api_request = AsyncMock(side_effect=ConnectionError("always fails"))

        # max_retries=2 means 3 total attempts allowed by the retry loop.
        # All three attempts raise -> RetryExhaustedError on the final iteration.
        with pytest.raises(RetryExhaustedError) as excinfo:
            await anthropic_client._request_with_retry(
                {"system_message": None, "api_messages": [], "tools": None}
            )
        # 3 attempts = max_retries + 1
        assert anthropic_client._make_api_request.await_count == 3
        assert isinstance(excinfo.value.last_exception, ConnectionError)

    @pytest.mark.asyncio
    async def test_retry_disabled_does_not_retry_on_error(self, openai_client):
        openai_client.retry_config = RetryConfig(enabled=False)
        openai_client._make_api_request = AsyncMock(side_effect=ConnectionError("boom"))
        with pytest.raises(ConnectionError):
            await openai_client._request_with_retry({"api_messages": [], "tools": None})
        # No retry decorator -> the raw call raises once and propagates.
        assert openai_client._make_api_request.await_count == 1

    @pytest.mark.asyncio
    async def test_openai_retry_calls_with_correct_splat_keys(self, openai_client):
        # When retries fire, the splat contract must keep working: keys returned
        # by _prepare_request must continue to satisfy _make_api_request's
        # named parameters even when the call fails the first time.
        openai_client.retry_config = RetryConfig(enabled=True, max_retries=2, initial_delay=0.0)
        openai_client._make_api_request = AsyncMock(
            side_effect=[ConnectionError("transient"), "OK"]
        )
        request_params = {"api_messages": [{"role": "user", "content": "hi"}], "tools": None}
        result = await openai_client._request_with_retry(request_params)
        assert result == "OK"
        # Both calls got the same kwargs splatted in.
        for call in openai_client._make_api_request.await_args_list:
            assert call.kwargs == request_params
