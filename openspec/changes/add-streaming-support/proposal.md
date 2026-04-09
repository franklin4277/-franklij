## Why

Currently, the Mini Agent waits for the LLM to generate complete responses before displaying anything to the user. This creates a poor user experience for long-running responses, as users see no feedback until the entire response is ready. Adding streaming support will make the agent feel much more responsive and provide real-time feedback.

## What Changes

- Add streaming response support to both Anthropic and OpenAI LLM clients
- Display streamed content incrementally as it arrives
- Show thinking content as it streams (for models that support extended thinking)
- Add a streaming mode toggle in configuration
- Preserve existing non-streaming behavior as the default

## Capabilities

### New Capabilities

- `streaming-responses`: Real-time streaming of LLM responses to the terminal, with incremental display of text and thinking content as it arrives

### Modified Capabilities

- (none - this is a purely additive feature)

## Impact

- **LLM Clients**: Modify `anthropic_client.py` and `openai_client.py` to support streaming
- **Agent Loop**: Update `agent.py` to handle streaming responses in the execution loop
- **Configuration**: Add optional `enable_streaming` setting in `llm` config section
- **Dependencies**: No new dependencies - httpx supports streaming natively
