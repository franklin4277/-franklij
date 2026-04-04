# Streaming LLM Responses — Implementation Plan

## Context

Issue #71 requests streaming output for LLM responses. Currently, `LLMClient.generate()` blocks until the complete response arrives, then prints it. For long responses, users see nothing until the model finishes thinking.

## Scope

This plan covers **LLM response streaming** — tokens arrive incrementally and are rendered in real-time. Tool execution remains unchanged (tools execute after the model completes tool call generation, per the current behavior).

**Out of scope:**
- Streaming tool output (covered by PR #81's `StreamingRenderer`)
- Streaming from MCP servers
- Server-Sent Events (SSE) API endpoints for external clients

## Background

### How the Current Agent Loop Works

```
run() loop
  └─ summarize_messages()
  └─ llm.generate(messages, tools)     ← blocks until full response
       └─ LLMResponse(content, thinking, tool_calls, finish_reason)
  └─ print thinking (if present)
  └─ print content (if present)
  └─ if tool_calls:
       └─ execute each tool
       └─ add tool result to messages
  └─ next iteration
```

### Streaming Changes This To

```
run() loop
  └─ summarize_messages()
  └─ for await chunk in llm.generate_stream(messages, tools):   ← returns incrementally
       ├─ if chunk.type == "thinking":
       │    └─ buffer thinking, render when complete
       ├─ if chunk.type == "content":
       │    └─ render content token
       ├─ if chunk.type == "tool_call_start":
       │    └─ start buffering new tool call
       ├─ if chunk.type == "tool_call_delta":
       │    └─ accumulate arguments
       └─ if chunk.type == "tool_call_complete":
            └─ execute tool, render result
  └─ if no tool_calls:
       └─ return final content
```

### Key Challenge: Partial Tool Call Buffering

Tool calls arrive as fragments. The model generates `<tool_use>` blocks incrementally — the `name` may arrive before `input`. We **cannot** execute a tool until we have the complete arguments. This requires buffering partial tool calls and only executing when `tool_call_complete` arrives.

## API Design

### New Schema Types

```python
# mini_agent/schema/schema.py

class StreamChunk(BaseModel):
    """A single chunk from a streaming LLM response."""
    type: Literal["thinking", "content", "tool_call_start", "tool_call_delta", "tool_call_complete", "done"]
    text: str | None = None          # For thinking / content chunks
    tool_call_id: str | None = None  # For tool call chunks
    tool_name: str | None = None    # For tool_call_start
    arguments: str | None = None    # For tool_call_delta (partial JSON string)
    tool_call: ToolCall | None = None  # For tool_call_complete (full tool call)
    finish_reason: str | None = None   # For done
    usage: TokenUsage | None = None    # For done
```

### LLMClientBase Changes

```python
# mini_agent/llm/base.py

class LLMClientBase(ABC):
    # ... existing methods ...

    @abstractmethod
    async def generate_stream(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream LLM response as async iterator of chunks.

        Args:
            messages: List of conversation messages
            tools: Optional list of available tools

        Yields:
            StreamChunk objects representing partial response
        """
        pass
```

### LLMClient Wrapper

```python
# mini_agent/llm/llm_wrapper.py

class LLMClient:
    # ... existing methods ...

    async def generate_stream(
        self,
        messages: list[Message],
        tools: list | None = None,
    ) -> AsyncIterator[StreamChunk]:
        return self._client.generate_stream(messages, tools)
```

## Implementation Steps

### Step 1: Schema & Types

**File:** `mini_agent/schema/schema.py`

Add `StreamChunk` model. Keep `LLMResponse` unchanged — existing code that calls `generate()` continues to work.

### Step 2: OpenAI Streaming Client

**File:** `mini_agent/llm/openai_client.py`

Add `generate_stream()` method:

```python
async def generate_stream(self, messages, tools=None) -> AsyncIterator[StreamChunk]:
    _, api_messages = self._convert_messages(messages)
    params = {
        "model": self.model,
        "messages": api_messages,
        "extra_body": {"reasoning_split": True},
        "stream": True,  # Enable streaming
    }
    if tools:
        params["tools"] = self._convert_tools(tools)

    stream = await self.client.chat.completions.create(**params)
    async for event in stream:
        chunk = self._parse_stream_chunk(event)
        if chunk:
            yield chunk
```

**Key:** `OpenAI` SDK's streaming response is an async iterator. Parse each `ChatCompletionChunk` event into a `StreamChunk`.

**Edge case:** Tool calls in OpenAI streaming come as a special `tool_calls` field with `index`, `function.name`, and `function.arguments` (as a partial JSON string). Buffer by `index` until the complete tool call arrives.

### Step 3: Anthropic Streaming Client

**File:** `mini_agent/llm/anthropic_client.py`

Add `generate_stream()` method:

```python
async def generate_stream(self, system_message, api_messages, tools=None) -> AsyncIterator[StreamChunk]:
    params = {
        "model": self.model,
        "max_tokens": 16384,
        "messages": api_messages,
        "stream": True,  # Enable streaming
    }
    if system_message:
        params["system"] = system_message
    if tools:
        params["tools"] = self._convert_tools(tools)

    async with self.client.messages.stream(**params) as stream:
        async for event in stream:
            chunk = self._parse_stream_chunk(event)
            if chunk:
                yield chunk
```

**Edge case:** Anthropic's streaming format has `content_block_delta` events with `type` (text/thinking) and `index`. Tool calls use `tool_use_delta` events. Need to buffer by `index` for both text blocks and tool calls.

### Step 4: Streaming Agent Loop

**File:** `mini_agent/agent.py`

Refactor `run()` to support both streaming and non-streaming modes. The streaming path processes chunks as they arrive.

**Key changes to `run()`:**
- Add `stream: bool = True` parameter
- On each chunk, render to terminal using ANSI escape sequences (overwrite last line)
- Buffer partial tool calls by ID
- When `tool_call_complete` arrives, execute the tool
- Collect `thinking` chunks separately, print when a complete thinking block arrives
- When `done` arrives with no tool calls, return the accumulated content

**Rendering logic:**
- Use `\r` (carriage return) to overwrite the current line for content tokens
- Print a newline when a complete thought/paragraph finishes
- Use PR #81's `StreamingRenderer` for stable + unstable line pattern

### Step 5: CLI Integration

**File:** `mini_agent/cli.py`

Add `--no-stream` flag to `run` command. When streaming is disabled, call `generate()` instead of `generate_stream()`. Default to streaming enabled.

```python
@click.command()
@click.option("--no-stream", is_flag=True, help="Disable streaming output")
async def run(no_stream: bool):
    agent = Agent(...)
    if no_stream:
        response = await agent.generate(...)
    else:
        async for chunk in agent.generate_stream(...):
            print(chunk, end="", flush=True)
```

### Step 6: Cancellation Support

Streaming must respect the existing `cancel_event`. When `cancel_event` is set:
1. Stop consuming from the stream iterator (don't make more API calls)
2. Discard accumulated partial chunks
3. Run `_cleanup_incomplete_messages()`
4. Return cancellation message

### Step 7: Tests

**File:** `tests/test_streaming.py` (new)

```python
# Coverage needed:
# - OpenAI streaming yields expected chunk types
# - Anthropic streaming yields expected chunk types
# - Partial tool calls are buffered correctly
# - Tool calls execute only when complete
# - Cancellation stops stream consumption
# - Token usage accumulated correctly
# - Thinking chunks buffered until complete
```

**File:** `tests/test_agent.py`

Add streaming variant of existing agent tests.

## Rendering Design

### Output Format

```
[Step 1/50] ───────────────────────────────────────────────────
Thinking: The user wants me to create a Python file...
         Let me break this down into steps...

🤖 Assistant: I'll help you create a Python file with the following structure:
  1. Import statements
  2. Class definition
  3. Main function

🔧 Tool Call: write_file
   Arguments:
    path: "hello.py"
    content: "print('hello world')\n"

✓ Result: Successfully wrote to hello.py
```

### Streaming rendering rules:
- **Thinking**: Render immediately as it arrives, don't buffer (user wants to see reasoning)
- **Content**: Print characters as they arrive, overwrite line if needed
- **Tool call headers**: Print when `tool_call_start` arrives (shows what tool is coming)
- **Tool arguments**: Buffer and display incrementally, show "..." if arguments are long
- **Tool execution**: Same as current — wait for `tool_call_complete`, execute, print result

## Compatibility

- `generate()` continues to work exactly as before (non-streaming default)
- Existing code that calls `agent.run()` without arguments gets streaming by default
- CLI `run` command gets streaming by default, `--no-stream` to disable
- MCP server uses non-streaming `generate()` internally (doesn't need streaming)

## Open Questions

1. **Should streaming be the default?** Yes — benefits most users. Power users scripting can opt out with `--no-stream`.

2. **Should thinking be rendered separately or inline with content?** Thinking renders in a collapsible `🧠 Thinking:` block before the content, not mixed inline.

3. **What if the stream is interrupted (network error)?** Fall back to non-streaming `generate()` as a retry mechanism.

4. **Tool arguments can be very large (file content).** Show first 200 chars + "..." + last 100 chars in the streaming display, full args when executing.

## Files to Modify

| File | Change Type |
|------|-------------|
| `mini_agent/schema/schema.py` | Add `StreamChunk` model |
| `mini_agent/llm/base.py` | Add `generate_stream()` abstract method |
| `mini_agent/llm/anthropic_client.py` | Implement `generate_stream()` |
| `mini_agent/llm/openai_client.py` | Implement `generate_stream()` |
| `mini_agent/llm/llm_wrapper.py` | Expose `generate_stream()` |
| `mini_agent/agent.py` | Add streaming loop in `run()` |
| `mini_agent/cli.py` | Add `--no-stream` flag |
| `tests/test_streaming.py` | New test file |
| `tests/test_agent.py` | Add streaming test variants |

## References

- Issue #71: https://github.com/MiniMax-AI/Mini-Agent/issues/71
- PR #81 (streaming renderer for tool output): https://github.com/MiniMax-AI/Mini-Agent/pull/81
- Anthropic streaming SDK: https://docs.anthropic.com/en/api/messages-streaming
- OpenAI streaming SDK: https://docs.openai.com/api-reference/chat/streaming
