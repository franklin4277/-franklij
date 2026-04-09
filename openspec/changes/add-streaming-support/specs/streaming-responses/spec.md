## ADDED Requirements

### Requirement: Streaming Response Support

The system SHALL provide streaming response support through a `stream_generate()` method on LLM clients that yields partial responses as content arrives.

#### Scenario: Streaming text content
- **WHEN** streaming is enabled and LLM generates a text response
- **THEN** text content SHALL be yielded incrementally as characters arrive
- **AND** each yield SHALL contain accumulated text seen so far

#### Scenario: Streaming thinking content
- **WHEN** streaming is enabled and LLM generates thinking content (extended thinking)
- **THEN** thinking content SHALL be yielded incrementally as blocks arrive
- **AND** the thinking content SHALL be properly separated from text content

#### Scenario: Streaming tool calls
- **WHEN** streaming is enabled and LLM generates tool calls
- **THEN** complete tool calls (with id, name, and all input) SHALL be yielded as they are finalized
- **AND** partial tool calls SHALL NOT be yielded until complete

#### Scenario: Non-streaming fallback
- **WHEN** streaming is disabled (default)
- **THEN** the existing `generate()` method SHALL return complete responses
- **AND** no streaming behavior SHALL be exhibited

### Requirement: Streaming Configuration

The system SHALL provide a configuration option to enable or disable streaming responses.

#### Scenario: Enable streaming via config
- **WHEN** user sets `llm.enable_streaming: true` in config.yaml
- **THEN** the agent SHALL use streaming mode when calling LLM clients

#### Scenario: Disable streaming via config
- **WHEN** user sets `llm.enable_streaming: false` or omits the setting
- **THEN** the agent SHALL use non-streaming mode (default behavior)

### Requirement: Streaming Display in Agent Loop

The system SHALL display streaming content to the terminal in a user-friendly manner.

#### Scenario: Display streamed text
- **WHEN** streaming text content arrives during agent execution
- **THEN** the content SHALL be displayed incrementally on the same line
- **AND** the display SHALL update smoothly without jitter

#### Scenario: Display streamed thinking
- **WHEN** streaming thinking content arrives during agent execution
- **THEN** the thinking SHALL be displayed with appropriate formatting (e.g., muted color)
- **AND** it SHALL be clearly distinguished from final text content

#### Scenario: Tool execution during streaming
- **WHEN** a complete tool call is received during streaming
- **THEN** the tool SHALL be executed immediately
- **AND** streaming of subsequent content SHALL continue after tool completion
