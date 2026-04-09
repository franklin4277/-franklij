"""Anthropic LLM client implementation."""

import logging
from typing import Any, AsyncGenerator

import anthropic

from ..retry import RetryConfig, async_retry
from ..schema import FunctionCall, LLMResponse, Message, TokenUsage, ToolCall
from .base import LLMClientBase

logger = logging.getLogger(__name__)


class AnthropicClient(LLMClientBase):
    """LLM client using Anthropic's protocol.

    This client uses the official Anthropic SDK and supports:
    - Extended thinking content
    - Tool calling
    - Retry logic
    """

    def __init__(
        self,
        api_key: str,
        api_base: str = "https://api.minimaxi.com/anthropic",
        model: str = "MiniMax-M2.5",
        retry_config: RetryConfig | None = None,
    ):
        """Initialize Anthropic client.

        Args:
            api_key: API key for authentication
            api_base: Base URL for the API (default: MiniMax Anthropic endpoint)
            model: Model name to use (default: MiniMax-M2.5)
            retry_config: Optional retry configuration
        """
        super().__init__(api_key, api_base, model, retry_config)

        # Initialize Anthropic async client
        self.client = anthropic.AsyncAnthropic(
            base_url=api_base,
            api_key=api_key,
            default_headers={"Authorization": f"Bearer {api_key}"},
        )

    async def _make_api_request(
        self,
        system_message: str | None,
        api_messages: list[dict[str, Any]],
        tools: list[Any] | None = None,
    ) -> anthropic.types.Message:
        """Execute API request (core method that can be retried).

        Args:
            system_message: Optional system message
            api_messages: List of messages in Anthropic format
            tools: Optional list of tools

        Returns:
            Anthropic Message response

        Raises:
            Exception: API call failed
        """
        params = {
            "model": self.model,
            "max_tokens": 16384,
            "messages": api_messages,
        }

        if system_message:
            params["system"] = system_message

        if tools:
            params["tools"] = self._convert_tools(tools)

        # Use Anthropic SDK's async messages.create
        response = await self.client.messages.create(**params)
        return response

    def _convert_tools(self, tools: list[Any]) -> list[dict[str, Any]]:
        """Convert tools to Anthropic format.

        Anthropic tool format:
        {
            "name": "tool_name",
            "description": "Tool description",
            "input_schema": {
                "type": "object",
                "properties": {...},
                "required": [...]
            }
        }

        Args:
            tools: List of Tool objects or dicts

        Returns:
            List of tools in Anthropic dict format
        """
        result = []
        for tool in tools:
            if isinstance(tool, dict):
                result.append(tool)
            elif hasattr(tool, "to_schema"):
                # Tool object with to_schema method
                result.append(tool.to_schema())
            else:
                raise TypeError(f"Unsupported tool type: {type(tool)}")
        return result

    def _convert_messages(
        self, messages: list[Message]
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """Convert internal messages to Anthropic format.

        Args:
            messages: List of internal Message objects

        Returns:
            Tuple of (system_message, api_messages)
        """
        system_message = None
        api_messages = []

        for msg in messages:
            if msg.role == "system":
                system_message = msg.content
                continue

            # For user and assistant messages
            if msg.role in ["user", "assistant"]:
                # Handle assistant messages with thinking or tool calls
                if msg.role == "assistant" and (msg.thinking or msg.tool_calls):
                    # Build content blocks for assistant with thinking and/or tool calls
                    content_blocks = []

                    # Add thinking block if present
                    if msg.thinking:
                        content_blocks.append(
                            {"type": "thinking", "thinking": msg.thinking}
                        )

                    # Add text content if present
                    if msg.content:
                        content_blocks.append({"type": "text", "text": msg.content})

                    # Add tool use blocks
                    if msg.tool_calls:
                        for tool_call in msg.tool_calls:
                            content_blocks.append(
                                {
                                    "type": "tool_use",
                                    "id": tool_call.id,
                                    "name": tool_call.function.name,
                                    "input": tool_call.function.arguments,
                                }
                            )

                    api_messages.append(
                        {"role": "assistant", "content": content_blocks}
                    )
                else:
                    api_messages.append({"role": msg.role, "content": msg.content})

            # For tool result messages
            elif msg.role == "tool":
                # Anthropic uses user role with tool_result content blocks
                api_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": msg.tool_call_id,
                                "content": msg.content,
                            }
                        ],
                    }
                )

        return system_message, api_messages

    def _prepare_request(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Prepare the request for Anthropic API.

        Args:
            messages: List of conversation messages
            tools: Optional list of available tools

        Returns:
            Dictionary containing request parameters
        """
        system_message, api_messages = self._convert_messages(messages)

        return {
            "system_message": system_message,
            "api_messages": api_messages,
            "tools": tools,
        }

    def _parse_response(self, response: anthropic.types.Message) -> LLMResponse:
        """Parse Anthropic response into LLMResponse.

        Args:
            response: Anthropic Message response

        Returns:
            LLMResponse object
        """
        # Extract text content, thinking, and tool calls
        text_content = ""
        thinking_content = ""
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                text_content += block.text
            elif block.type == "thinking":
                thinking_content += block.thinking
            elif block.type == "tool_use":
                # Parse Anthropic tool_use block
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        type="function",
                        function=FunctionCall(
                            name=block.name,
                            arguments=block.input,
                        ),
                    )
                )

        # Extract token usage from response
        # Anthropic usage includes: input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens
        usage = None
        if hasattr(response, "usage") and response.usage:
            input_tokens = response.usage.input_tokens or 0
            output_tokens = response.usage.output_tokens or 0
            cache_read_tokens = (
                getattr(response.usage, "cache_read_input_tokens", 0) or 0
            )
            cache_creation_tokens = (
                getattr(response.usage, "cache_creation_input_tokens", 0) or 0
            )
            total_input_tokens = (
                input_tokens + cache_read_tokens + cache_creation_tokens
            )
            usage = TokenUsage(
                prompt_tokens=total_input_tokens,
                completion_tokens=output_tokens,
                total_tokens=total_input_tokens + output_tokens,
            )

        return LLMResponse(
            content=text_content,
            thinking=thinking_content if thinking_content else None,
            tool_calls=tool_calls if tool_calls else None,
            finish_reason=response.stop_reason or "stop",
            usage=usage,
        )

    async def generate(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
    ) -> LLMResponse:
        """Generate response from Anthropic LLM.

        Args:
            messages: List of conversation messages
            tools: Optional list of available tools

        Returns:
            LLMResponse containing the generated content
        """
        # Prepare request
        request_params = self._prepare_request(messages, tools)

        # Make API request with retry logic
        if self.retry_config.enabled:
            # Apply retry logic
            retry_decorator = async_retry(
                config=self.retry_config, on_retry=self.retry_callback
            )
            api_call = retry_decorator(self._make_api_request)
            response = await api_call(
                request_params["system_message"],
                request_params["api_messages"],
                request_params["tools"],
            )
        else:
            # Don't use retry
            response = await self._make_api_request(
                request_params["system_message"],
                request_params["api_messages"],
                request_params["tools"],
            )

        # Parse and return response
        return self._parse_response(response)

    async def stream_generate(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
    ) -> AsyncGenerator[LLMResponse, None]:
        """Stream response from Anthropic LLM.

        Yields partial LLMResponse objects as content arrives.

        Args:
            messages: List of conversation messages
            tools: Optional list of Tool objects or dicts

        Yields:
            LLMResponse containing partial/generated content, thinking, and tool calls
        """
        request_params = self._prepare_request(messages, tools)

        params = {
            "model": self.model,
            "max_tokens": 16384,
            "messages": request_params["api_messages"],
        }

        if request_params["system_message"]:
            params["system"] = request_params["system_message"]

        if tools:
            params["tools"] = self._convert_tools(tools)

        accumulated_text = ""
        accumulated_thinking = ""
        accumulated_tool_calls: list[ToolCall] = []
        pending_tool_call: dict[str, Any] | None = None

        async with self.client.messages.stream(**params) as stream:
            async for event in stream:
                if event.type == "content_block_delta":
                    if event.delta.type == "thinking_delta":
                        accumulated_thinking += event.delta.thinking
                        yield LLMResponse(
                            content=accumulated_text,
                            thinking=accumulated_thinking
                            if accumulated_thinking
                            else None,
                            tool_calls=accumulated_tool_calls
                            if accumulated_tool_calls
                            else None,
                            finish_reason="",
                            usage=None,
                        )
                    elif event.delta.type == "text_delta":
                        accumulated_text += event.delta.text
                        yield LLMResponse(
                            content=accumulated_text,
                            thinking=accumulated_thinking
                            if accumulated_thinking
                            else None,
                            tool_calls=accumulated_tool_calls
                            if accumulated_tool_calls
                            else None,
                            finish_reason="",
                            usage=None,
                        )
                elif event.type == "tool_use_delta":
                    if pending_tool_call is None:
                        pending_tool_call = {"id": "", "name": "", "input": {}}
                    if event.delta.name:
                        pending_tool_call["name"] = event.delta.name
                    if event.delta.input:
                        if "input" not in pending_tool_call:
                            pending_tool_call["input"] = {}
                        pending_tool_call["input"].update(event.delta.input)
                elif event.type == "tool_use_block":
                    if pending_tool_call and pending_tool_call.get("name"):
                        accumulated_tool_calls.append(
                            ToolCall(
                                id=pending_tool_call["id"] or event.content_block.id,
                                type="function",
                                function=FunctionCall(
                                    name=pending_tool_call["name"],
                                    arguments=pending_tool_call.get("input", {}),
                                ),
                            )
                        )
                        pending_tool_call = None
                        yield LLMResponse(
                            content=accumulated_text,
                            thinking=accumulated_thinking
                            if accumulated_thinking
                            else None,
                            tool_calls=accumulated_tool_calls
                            if accumulated_tool_calls
                            else None,
                            finish_reason="",
                            usage=None,
                        )
                elif event.type == "message_delta":
                    if event.delta.stop_reason:
                        yield LLMResponse(
                            content=accumulated_text,
                            thinking=accumulated_thinking
                            if accumulated_thinking
                            else None,
                            tool_calls=accumulated_tool_calls
                            if accumulated_tool_calls
                            else None,
                            finish_reason=event.delta.stop_reason,
                            usage=None,
                        )

        if accumulated_tool_calls and pending_tool_call:
            accumulated_tool_calls.append(
                ToolCall(
                    id=pending_tool_call["id"] or "final",
                    type="function",
                    function=FunctionCall(
                        name=pending_tool_call["name"],
                        arguments=pending_tool_call.get("input", {}),
                    ),
                )
            )

        final_response = await stream.get_final_message()
        usage = None
        if final_response.usage:
            input_tokens = final_response.usage.input_tokens or 0
            output_tokens = final_response.usage.output_tokens or 0
            cache_read_tokens = (
                getattr(final_response.usage, "cache_read_input_tokens", 0) or 0
            )
            cache_creation_tokens = (
                getattr(final_response.usage, "cache_creation_input_tokens", 0) or 0
            )
            total_input_tokens = (
                input_tokens + cache_read_tokens + cache_creation_tokens
            )
            usage = TokenUsage(
                prompt_tokens=total_input_tokens,
                completion_tokens=output_tokens,
                total_tokens=total_input_tokens + output_tokens,
            )

        yield LLMResponse(
            content=accumulated_text,
            thinking=accumulated_thinking if accumulated_thinking else None,
            tool_calls=accumulated_tool_calls if accumulated_tool_calls else None,
            finish_reason="stop",
            usage=usage,
        )
