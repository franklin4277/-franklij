## Context

The Mini Agent currently uses a blocking approach where it waits for the complete LLM response before displaying anything to users. For long responses, this creates a poor experience with no feedback during generation.

The LLM clients (Anthropic and OpenAI) both support streaming APIs. The Anthropic SDK uses `messages.stream` and the OpenAI SDK uses `chat.completions.create` with streaming. Both SDKs support receiving intermediate content blocks as they arrive.

Key constraints:
- Must maintain backward compatibility (streaming off by default)
- Must support both Anthropic and OpenAI protocols
- Must handle the interleaved thinking format for MiniMax-M2.5
- Terminal output should be smooth and not jittery

## Goals / Non-Goals

**Goals:**
- Add streaming response support to LLM clients via a new `stream_generate()` method
- Display streamed text content incrementally in the agent loop
- Show streamed thinking content as it arrives (Anthropic thinking blocks, OpenAI reasoning_details)
- Add configuration toggle `enable_streaming` in LLM config
- Preserve existing non-streaming behavior as the default

**Non-Goals:**
- Not implementing server-sent events (SSE) for external consumers
- Not adding streaming to the ACP server (this is for CLI output only)
- Not changing the message history storage format

## Decisions

### 1. Add `stream_generate()` method to LLM clients instead of modifying `generate()`

**Decision:** Create a new `stream_generate()` async generator method in `LLMClientBase` and implement it in each client.

**Rationale:** This keeps the existing `generate()` method unchanged for backward compatibility and allows callers to choose between streaming and non-streaming modes. It's cleaner than adding a `stream=True` parameter that would complicate the retry logic.

**Alternatives considered:**
- Add `stream=True` parameter to `generate()`: Would complicate retry logic (can't retry streaming), and would require significant refactoring of the existing method signature
- Use a separate `StreamingLLMClient` class: Would duplicate code between streaming and non-streaming clients

### 2. Use ANSI terminal controls for smooth streaming output

**Decision:** Use carriage return (`\r`) to overwrite lines and flush output frequently for smooth display.

**Rationale:** This provides the most responsive-feeling output. The agent already uses ANSI color codes extensively, so this fits the existing codebase style.

**Alternatives considered:**
- Collect full response and display at end: This defeats the purpose of streaming
- Use prompt-toolkit features: Would require significant changes to the CLI session management

### 3. Yield partial `LLMResponse` objects from stream_generate()

**Decision:** The streaming method yields partial `LLMResponse` objects as content arrives, with accumulated content/thinking and any new tool calls.

**Rationale:** This allows the agent loop to process partial responses uniformly. The response structure is already designed to support incremental content (content is a string, not a list of blocks at this level).

**Alternatives considered:**
- Yield raw content blocks: Would require changing how the agent loop processes responses
- Yield specialized `StreamingResponse` type: Would require additional type handling in agent.py

### 4. Add stream_generate to LLMClient wrapper

**Decision:** Add `stream_generate()` method to the `LLMClient` wrapper class to expose streaming to callers.

**Rationale:** The wrapper is what most code uses, so it needs to expose the streaming method for consistency.

## Risks / Trade-offs

[Risk] Terminal may not handle rapid output well on Windows
→ **Mitigation:** Use `sys.stdout.flush()` after each write. The existing codebase already uses print() extensively, so this should work.

[Risk] Streaming may interfere with user input/commands
→ **Mitigation:** Streaming only happens during agent execution, not during user input. The CLI loop is not changed.

[Risk] Retry logic doesn't work with streaming
→ **Mitigation:** `stream_generate()` does not use retry logic. If a streaming request fails, the user sees the error and can retry. Non-streaming `generate()` continues to support retries.

[Risk] Tool calls may arrive incrementally during streaming
→ **Mitigation:** The agent loop will need to handle partial tool calls. When a tool_use block is complete (has id, name, input), process it immediately rather than waiting for the full response.

[Risk] MiniMax-M2.5 model does not generate tool_use blocks in streaming mode
→ **Status:** Confirmed model behavior issue. Streaming code is correct but model doesn't emit tool calls when using streaming API.
→ **Workaround:** Keep `enable_streaming: false` for tasks requiring tool calling.

## Migration Plan

1. **Phase 1:** Add `stream_generate()` method to `LLMClientBase` and both clients (no behavior change yet)
2. **Phase 2:** Add `enable_streaming` config option to `LLMConfig`
3. **Phase 3:** Modify `agent.py` to use streaming when enabled, with graceful fallback
4. **Phase 4:** Add `stream_generate()` to `LLMClient` wrapper
5. **Phase 5:** Test both streaming and non-streaming modes

**Rollback:** Set `enable_streaming: false` or remove the config option to revert to non-streaming behavior.
