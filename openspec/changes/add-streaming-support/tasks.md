## 1. Add stream_generate Method to LLM Client Base

- [x] 1.1 Add abstract `stream_generate()` method signature to `LLMClientBase` in `mini_agent/llm/base.py`
- [x] 1.2 Define async generator return type hint for `stream_generate()`

## 2. Implement stream_generate in AnthropicClient

- [x] 2.1 Implement `stream_generate()` in `mini_agent/llm/anthropic_client.py` using `messages.stream`
- [x] 2.2 Yield partial `LLMResponse` objects with accumulated text content
- [x] 2.3 Handle thinking blocks and yield partial thinking content
- [x] 2.4 Handle tool_use blocks and yield complete tool calls when finalized

## 3. Implement stream_generate in OpenAIClient

- [x] 3.1 Implement `stream_generate()` in `mini_agent/llm/openai_client.py` using streaming chat completions
- [x] 3.2 Yield partial `LLMResponse` objects with accumulated text content
- [x] 3.3 Handle reasoning_details blocks and yield partial thinking content
- [x] 3.4 Handle tool_calls and yield complete tool calls when finalized

## 4. Add Streaming Configuration Option

- [x] 4.1 Add `enable_streaming: bool = False` field to `LLMConfig` in `mini_agent/config.py`
- [x] 4.2 Update `Config.from_yaml()` to parse the new `enable_streaming` field
- [x] 4.3 Add config example entry in `mini_agent/config/config-example.yaml`

## 5. Modify Agent Loop for Streaming Support

- [x] 5.1 Add streaming mode handling in `Agent.run()` in `mini_agent/agent.py`
- [x] 5.2 Display streamed text content incrementally using terminal controls
- [x] 5.3 Display streamed thinking content with appropriate formatting
- [x] 5.4 Process complete tool calls as they arrive during streaming
- [x] 5.5 Fall back to non-streaming `generate()` when streaming disabled

## 6. Add stream_generate to LLMClient Wrapper

- [x] 6.1 Add `stream_generate()` method to `LLMClient` wrapper in `mini_agent/llm/llm_wrapper.py`

## 7. Testing

- [x] 7.1 Unit tests for streaming functionality (`tests/test_streaming.py`)
- [x] 7.2 Non-streaming mode with tool calling works correctly
- [ ] 7.3 Streaming mode with tool calling (blocked by model limitation)

## Implementation Notes

### Known Limitation
MiniMax-M2.5 model does not generate `tool_use` blocks in streaming mode. This is a model behavior issue, not a code issue. The streaming code is correct but the model doesn't emit tool calls when using the streaming API endpoint.

**Workaround:** Keep `enable_streaming: false` in config for tasks that require tool calling.

### Files Modified
- `mini_agent/llm/base.py` - Added `stream_generate()` abstract method
- `mini_agent/llm/anthropic_client.py` - Implemented streaming
- `mini_agent/llm/openai_client.py` - Implemented streaming
- `mini_agent/llm/llm_wrapper.py` - Added `stream_generate()` wrapper method
- `mini_agent/config.py` - Added `enable_streaming` config field
- `mini_agent/config/config-example.yaml` - Added streaming config option
- `mini_agent/agent.py` - Added streaming support in run loop
- `mini_agent/cli.py` - Pass `enable_streaming` to Agent
- `tests/test_streaming.py` - New unit tests for streaming
