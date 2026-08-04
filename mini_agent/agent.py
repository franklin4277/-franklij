"""Core Agent implementation."""

import asyncio
import json
from pathlib import Path
from time import perf_counter
from typing import Optional

import tiktoken

from .llm import LLMClient
from .logger import AgentLogger
from .schema import Message
from .tools import Tool, ToolResult
from .terminal import Colors, calculate_display_width
from .core.events import AgentCompletedEvent


class Agent:
    """Single agent with basic tools and MCP support."""

    def __init__(
        self,
        llm_client: LLMClient,
        system_prompt: str,
        tools: list[Tool] | None = None,
        max_steps: int = 50,
        workspace_dir: str = "./workspace",
        token_limit: int = 80000,  # Summary triggered when tokens exceed this value
        box_width: int = 58,  # Terminal box display width
        tool_arg_truncate_len: int = 200,  # Truncate tool args longer than this in display
        tool_result_truncate_len: int = 300,  # Truncate tool results longer than this in display
        plugins: "PluginRegistry | None" = None,
    ):
        self.llm = llm_client
        # Tools come from three sources (in order):
        #   1. `plugins` registry (Tools + MCP + Skills) - the new way
        #   2. `tools` list (legacy / direct) - backward compatible
        self.plugins = plugins
        base_tools: list[Tool] = list(tools or [])
        if plugins is not None:
            base_tools.extend(plugins.all_tools())
            # Append skills' system prompt additions
            skill_prompt = plugins.system_prompt_addition()
            if skill_prompt and "{SKILLS_METADATA}" in system_prompt:
                system_prompt = system_prompt.replace("{SKILLS_METADATA}", skill_prompt)
            elif skill_prompt:
                system_prompt = system_prompt + "\n\n" + skill_prompt
            elif "{SKILLS_METADATA}" in system_prompt:
                # Plugins enabled but no skills discovered: strip the placeholder
                # so the literal token never reaches the LLM.
                system_prompt = system_prompt.replace("{SKILLS_METADATA}", "")
        elif "{SKILLS_METADATA}" in system_prompt:
            system_prompt = system_prompt.replace("{SKILLS_METADATA}", "")
        self.tools = {tool.name: tool for tool in base_tools}
        self.max_steps = max_steps
        self.token_limit = token_limit
        self.box_width = box_width
        self.tool_arg_truncate_len = tool_arg_truncate_len
        self.tool_result_truncate_len = tool_result_truncate_len
        self.workspace_dir = Path(workspace_dir)
        # Cancellation event for interrupting agent execution (set externally, e.g., by Esc key)
        self.cancel_event: Optional[asyncio.Event] = None

        # Ensure workspace exists
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

        # Inject workspace information into system prompt if not already present
        if "Current Workspace" not in system_prompt:
            workspace_info = f"\n\n## Current Workspace\nYou are currently working in: `{self.workspace_dir.absolute()}`\nAll relative paths will be resolved relative to this directory."
            system_prompt = system_prompt + workspace_info

        self.system_prompt = system_prompt

        # Initialize message history
        self.messages: list[Message] = [Message(role="system", content=system_prompt)]

        # Initialize logger
        self.logger = AgentLogger()

        # Token usage from last API response (updated after each LLM call)
        self.api_total_tokens: int = 0
        # Flag to skip token check right after summary (avoid consecutive triggers)
        self._skip_next_token_check: bool = False

    def add_tool(self, tool) -> None:
        """Register a tool after Agent construction (e.g. from a plugin)."""
        self.tools[tool.name] = tool

    async def run_with_orchestrator(
        self,
        message: str,
        cancel_event=None,
        max_steps: int | None = None,
    ) -> str:
        """Run the agent via ReActOrchestrator (new path, no rich CLI output).

        Use this for SSE streaming, sub-agents, or when you want plain
        output. For the rich CLI experience, use the legacy run() instead.

        Returns the final assistant message text.
        """
        from .core.orchestrator import ReActOrchestrator

        if cancel_event is not None:
            self.cancel_event = cancel_event
        steps = max_steps or self.max_steps

        result = None
        async for ev in self.stream(message, max_steps=steps):
            if isinstance(ev, AgentCompletedEvent):
                result = ev.final_result
        return result or ""

    async def execute_tool(self, tool_call) -> ToolResult:
        """Execute a single tool call. Used by Orchestrator.

        Args:
            tool_call: object with .id, .function.name, .function.arguments

        Returns:
            ToolResult
        """
        function_name = tool_call.function.name
        arguments = tool_call.function.arguments or {}
        return await self._execute_one_tool(function_name, arguments)

    async def stream(self, message: str, **opts):
        """Stream AgentEvents via Orchestrator (new API).

        Yields AgentEvent instances. Does NOT replace run() (which has
        richer logging/output). Use this for streaming UI / sub-agents.

        Usage:
            async for event in agent.stream("query"):
                if isinstance(event, AgentCompletedEvent):
                    print(event.final_result)
        """
        from .core.orchestrator import ReActOrchestrator
        from .core.events import AgentCompletedEvent

        # Add user message to history
        self.add_user_message(message)
        orch = ReActOrchestrator(max_steps=self.max_steps)
        async for event in orch.stream(self, message, **opts):
            yield event

    def add_user_message(self, content: str):
        """Add a user message to history."""
        self.messages.append(Message(role="user", content=content))

    def _check_cancelled(self) -> bool:
        """Check if agent execution has been cancelled.

        Returns:
            True if cancelled, False otherwise.
        """
        if self.cancel_event is not None and self.cancel_event.is_set():
            return True
        return False

    def _cleanup_incomplete_messages(self):
        """Remove the incomplete assistant message and its partial tool results.

        This ensures message consistency after cancellation by removing
        only the current step's incomplete messages, preserving completed steps.
        """
        # Find the index of the last assistant message
        last_assistant_idx = -1
        for i in range(len(self.messages) - 1, -1, -1):
            if self.messages[i].role == "assistant":
                last_assistant_idx = i
                break

        if last_assistant_idx == -1:
            # No assistant message found, nothing to clean
            return

        # Remove the last assistant message and all tool results after it
        removed_count = len(self.messages) - last_assistant_idx
        if removed_count > 0:
            self.messages = self.messages[:last_assistant_idx]
            print(f"{Colors.DIM}   Cleaned up {removed_count} incomplete message(s){Colors.RESET}")

    def _estimate_tokens(self) -> int:
        """Accurately calculate token count for message history using tiktoken

        Uses cl100k_base encoder (GPT-4/Claude/M2 compatible)
        """
        try:
            # Use cl100k_base encoder (used by GPT-4 and most modern models)
            encoding = tiktoken.get_encoding("cl100k_base")
        except Exception:
            # Fallback: if tiktoken initialization fails, use simple estimation
            return self._estimate_tokens_fallback()

        total_tokens = 0

        for msg in self.messages:
            # Count text content
            if isinstance(msg.content, str):
                total_tokens += len(encoding.encode(msg.content))
            elif isinstance(msg.content, list):
                for block in msg.content:
                    if isinstance(block, dict):
                        # Convert dict to string for calculation
                        total_tokens += len(encoding.encode(str(block)))

            # Count thinking
            if msg.thinking:
                total_tokens += len(encoding.encode(msg.thinking))

            # Count tool_calls
            if msg.tool_calls:
                total_tokens += len(encoding.encode(str(msg.tool_calls)))

            # Metadata overhead per message (approximately 4 tokens)
            total_tokens += 4

        return total_tokens

    def _estimate_tokens_fallback(self) -> int:
        """Fallback token estimation method (when tiktoken is unavailable)"""
        total_chars = 0
        for msg in self.messages:
            if isinstance(msg.content, str):
                total_chars += len(msg.content)
            elif isinstance(msg.content, list):
                for block in msg.content:
                    if isinstance(block, dict):
                        total_chars += len(str(block))

            if msg.thinking:
                total_chars += len(msg.thinking)

            if msg.tool_calls:
                total_chars += len(str(msg.tool_calls))

        # Rough estimation: average 2.5 characters = 1 token
        return int(total_chars / 2.5)

    async def _summarize_messages(self):
        """Message history summarization: summarize conversations between user messages when tokens exceed limit

        Strategy (Agent mode):
        - Keep all user messages (these are user intents)
        - Summarize content between each user-user pair (agent execution process)
        - If last round is still executing (has agent/tool messages but no next user), also summarize
        - Structure: system -> user1 -> summary1 -> user2 -> summary2 -> user3 -> summary3 (if executing)

        Summary is triggered when EITHER:
        - Local token estimation exceeds limit
        - API reported total_tokens exceeds limit
        """
        # Skip check if we just completed a summary (wait for next LLM call to update api_total_tokens)
        if self._skip_next_token_check:
            self._skip_next_token_check = False
            return

        estimated_tokens = self._estimate_tokens()

        # Check both local estimation and API reported tokens
        should_summarize = estimated_tokens > self.token_limit or self.api_total_tokens > self.token_limit

        # If neither exceeded, no summary needed
        if not should_summarize:
            return

        print(
            f"\n{Colors.BRIGHT_YELLOW}📊 Token usage - Local estimate: {estimated_tokens}, API reported: {self.api_total_tokens}, Limit: {self.token_limit}{Colors.RESET}"
        )
        print(f"{Colors.BRIGHT_YELLOW}🔄 Triggering message history summarization...{Colors.RESET}")

        # Find all user message indices (skip system prompt)
        user_indices = [i for i, msg in enumerate(self.messages) if msg.role == "user" and i > 0]

        # Need at least 1 user message to perform summary
        if len(user_indices) < 1:
            print(f"{Colors.BRIGHT_YELLOW}⚠️  Insufficient messages, cannot summarize{Colors.RESET}")
            return

        # Build new message list
        new_messages = [self.messages[0]]  # Keep system prompt
        summary_count = 0

        # Iterate through each user message and summarize the execution process after it
        for i, user_idx in enumerate(user_indices):
            # Add current user message
            new_messages.append(self.messages[user_idx])

            # Determine message range to summarize
            # If last user, go to end of message list; otherwise to before next user
            if i < len(user_indices) - 1:
                next_user_idx = user_indices[i + 1]
            else:
                next_user_idx = len(self.messages)

            # Extract execution messages for this round
            execution_messages = self.messages[user_idx + 1 : next_user_idx]

            # If there are execution messages in this round, summarize them
            if execution_messages:
                summary_text = await self._create_summary(execution_messages, i + 1)
                if summary_text:
                    summary_message = Message(
                        role="user",
                        content=f"[Assistant Execution Summary]\n\n{summary_text}",
                    )
                    new_messages.append(summary_message)
                    summary_count += 1

        # Replace message list
        self.messages = new_messages

        # Skip next token check to avoid consecutive summary triggers
        # (api_total_tokens will be updated after next LLM call)
        self._skip_next_token_check = True

        new_tokens = self._estimate_tokens()
        print(f"{Colors.BRIGHT_GREEN}✓ Summary completed, local tokens: {estimated_tokens} → {new_tokens}{Colors.RESET}")
        print(f"{Colors.DIM}  Structure: system + {len(user_indices)} user messages + {summary_count} summaries{Colors.RESET}")
        print(f"{Colors.DIM}  Note: API token count will update on next LLM call{Colors.RESET}")

    async def _create_summary(self, messages: list[Message], round_num: int) -> str:
        """Create summary for one execution round

        Args:
            messages: List of messages to summarize
            round_num: Round number

        Returns:
            Summary text
        """
        if not messages:
            return ""

        # Build summary content
        summary_content = f"Round {round_num} execution process:\n\n"
        for msg in messages:
            if msg.role == "assistant":
                content_text = msg.content if isinstance(msg.content, str) else str(msg.content)
                summary_content += f"Assistant: {content_text}\n"
                if msg.tool_calls:
                    tool_names = [tc.function.name for tc in msg.tool_calls]
                    summary_content += f"  → Called tools: {', '.join(tool_names)}\n"
            elif msg.role == "tool":
                result_preview = msg.content if isinstance(msg.content, str) else str(msg.content)
                summary_content += f"  ← Tool returned: {result_preview}...\n"

        # Call LLM to generate concise summary
        try:
            summary_prompt = f"""Please provide a concise summary of the following Agent execution process:

{summary_content}

Requirements:
1. Focus on what tasks were completed and which tools were called
2. Keep key execution results and important findings
3. Be concise and clear, within 1000 words
4. Use English
5. Do not include "user" related content, only summarize the Agent's execution process"""

            summary_msg = Message(role="user", content=summary_prompt)
            response = await self.llm.generate(
                messages=[
                    Message(
                        role="system",
                        content="You are an assistant skilled at summarizing Agent execution processes.",
                    ),
                    summary_msg,
                ]
            )

            summary_text = response.content
            print(f"{Colors.BRIGHT_GREEN}✓ Summary for round {round_num} generated successfully{Colors.RESET}")
            return summary_text

        except Exception as e:
            print(f"{Colors.BRIGHT_RED}✗ Summary generation failed for round {round_num}: {e}{Colors.RESET}")
            # Use simple text summary on failure
            return summary_content

    # ---- run() helpers -------------------------------------------------------
    def _emit_step_header(self, step: int) -> None:
        """Print the box-drawing header announcing the current step."""
        box_width = self.box_width
        step_text = f"{Colors.BOLD}{Colors.BRIGHT_CYAN}💭 Step {step + 1}/{self.max_steps}{Colors.RESET}"
        step_display_width = calculate_display_width(step_text)
        padding = max(0, box_width - 1 - step_display_width)  # -1 for leading space

        print(f"\n{Colors.DIM}╭{'─' * box_width}╮{Colors.RESET}")
        print(f"{Colors.DIM}│{Colors.RESET} {step_text}{' ' * padding}{Colors.DIM}│{Colors.RESET}")
        print(f"{Colors.DIM}╰{'─' * box_width}╯{Colors.RESET}")

    def _emit_step_footer(self, step: int, step_start_time: float, run_start_time: float) -> None:
        """Print the elapsed-time line closing out the current step."""
        step_elapsed = perf_counter() - step_start_time
        total_elapsed = perf_counter() - run_start_time
        print(f"\n{Colors.DIM}⏱️  Step {step + 1} completed in {step_elapsed:.2f}s (total: {total_elapsed:.2f}s){Colors.RESET}")

    def _cancel_and_cleanup(self) -> str:
        """Drop the incomplete step, announce cancellation, return the message."""
        self._cleanup_incomplete_messages()
        cancel_msg = "Task cancelled by user."
        print(f"\n{Colors.BRIGHT_YELLOW}⚠️  {cancel_msg}{Colors.RESET}")
        return cancel_msg

    def _format_llm_error(self, e: Exception) -> str:
        """Announce a failed LLM call and return the message run() should yield."""
        # Check if it's a retry exhausted error
        from .logger import RetryExhaustedError

        if isinstance(e, RetryExhaustedError):
            error_msg = f"LLM call failed after {e.attempts} retries\nLast error: {str(e.last_exception)}"
            print(f"\n{Colors.BRIGHT_RED}❌ Retry failed:{Colors.RESET} {error_msg}")
        else:
            error_msg = f"LLM call failed: {str(e)}"
            print(f"\n{Colors.BRIGHT_RED}❌ Error:{Colors.RESET} {error_msg}")
        return error_msg

    def _record_llm_response(self, response) -> None:
        """Accumulate token usage, log the response, append the assistant message."""
        # Accumulate API reported token usage
        if response.usage:
            self.api_total_tokens = response.usage.total_tokens

        self.logger.log_response(
            content=response.content,
            thinking=response.thinking,
            tool_calls=response.tool_calls,
            finish_reason=response.finish_reason,
        )

        self.messages.append(
            Message(
                role="assistant",
                content=response.content,
                thinking=response.thinking,
                tool_calls=response.tool_calls,
            )
        )

    def _emit_assistant_output(self, response) -> None:
        """Print the assistant's thinking and reply, when present."""
        if response.thinking:
            print(f"\n{Colors.BOLD}{Colors.MAGENTA}🧠 Thinking:{Colors.RESET}")
            print(f"{Colors.DIM}{response.thinking}{Colors.RESET}")

        if response.content:
            print(f"\n{Colors.BOLD}{Colors.BRIGHT_BLUE}🤖 Assistant:{Colors.RESET}")
            print(f"{response.content}")

    def _emit_tool_call(self, function_name: str, arguments: dict) -> None:
        """Print the tool name and its arguments, truncating long values."""
        print(f"\n{Colors.BRIGHT_YELLOW}🔧 Tool Call:{Colors.RESET} {Colors.BOLD}{Colors.CYAN}{function_name}{Colors.RESET}")

        # Arguments (formatted display)
        print(f"{Colors.DIM}   Arguments:{Colors.RESET}")
        # Truncate each argument value to avoid overly long output
        truncated_args = {}
        for key, value in arguments.items():
            value_str = str(value)
            if len(value_str) > self.tool_arg_truncate_len:
                truncated_args[key] = value_str[: self.tool_arg_truncate_len] + "..."
            else:
                truncated_args[key] = value
        args_json = json.dumps(truncated_args, indent=2, ensure_ascii=False)
        for line in args_json.split("\n"):
            print(f"   {Colors.DIM}{line}{Colors.RESET}")

    async def _execute_one_tool(self, function_name: str, arguments: dict) -> ToolResult:
        """Run a single tool call, converting any failure into a failed ToolResult."""
        if function_name not in self.tools:
            return ToolResult(
                success=False,
                content="",
                error=f"Unknown tool: {function_name}",
            )
        try:
            tool = self.tools[function_name]
            return await tool.execute(**arguments)
        except Exception as e:
            # Catch all exceptions during tool execution, convert to failed ToolResult
            import traceback

            error_detail = f"{type(e).__name__}: {str(e)}"
            error_trace = traceback.format_exc()
            return ToolResult(
                success=False,
                content="",
                error=f"Tool execution failed: {error_detail}\n\nTraceback:\n{error_trace}",
            )

    def _emit_tool_result(self, result: ToolResult) -> None:
        """Print a preview of the tool result, or the error if it failed."""
        if result.success:
            result_text = result.content
            if len(result_text) > self.tool_result_truncate_len:
                result_text = result_text[: self.tool_result_truncate_len] + f"{Colors.DIM}...{Colors.RESET}"
            print(f"{Colors.BRIGHT_GREEN}✓ Result:{Colors.RESET} {result_text}")
        else:
            print(f"{Colors.BRIGHT_RED}✗ Error:{Colors.RESET} {Colors.RED}{result.error}{Colors.RESET}")

    async def run(self, cancel_event: Optional[asyncio.Event] = None) -> str:
        """Execute agent loop until task is complete or max steps reached.

        Args:
            cancel_event: Optional asyncio.Event that can be set to cancel execution.
                          When set, the agent will stop at the next safe checkpoint
                          (after completing the current step to keep messages consistent).

        Returns:
            The final response content, or error message (including cancellation message).
        """
        # Set cancellation event (can also be set via self.cancel_event before calling run())
        if cancel_event is not None:
            self.cancel_event = cancel_event

        # Start new run, initialize log file
        self.logger.start_new_run()
        print(f"{Colors.DIM}📝 Log file: {self.logger.get_log_file_path()}{Colors.RESET}")

        step = 0
        run_start_time = perf_counter()

        while step < self.max_steps:
            # Check for cancellation at start of each step
            if self._check_cancelled():
                return self._cancel_and_cleanup()

            step_start_time = perf_counter()
            # Check and summarize message history to prevent context overflow
            await self._summarize_messages()

            self._emit_step_header(step)

            # Get tool list for LLM call
            tool_list = list(self.tools.values())

            # Log LLM request and call LLM with Tool objects directly
            self.logger.log_request(messages=self.messages, tools=tool_list)

            try:
                response = await self.llm.generate(messages=self.messages, tools=tool_list)
            except Exception as e:
                return self._format_llm_error(e)

            self._record_llm_response(response)
            self._emit_assistant_output(response)

            # Check if task is complete (no tool calls)
            if not response.tool_calls:
                self._emit_step_footer(step, step_start_time, run_start_time)
                return response.content

            # Check for cancellation before executing tools
            if self._check_cancelled():
                return self._cancel_and_cleanup()

            # Execute tool calls
            for tool_call in response.tool_calls:
                tool_call_id = tool_call.id
                function_name = tool_call.function.name
                arguments = tool_call.function.arguments

                self._emit_tool_call(function_name, arguments)

                result = await self._execute_one_tool(function_name, arguments)

                # Log tool execution result
                self.logger.log_tool_result(
                    tool_name=function_name,
                    arguments=arguments,
                    result_success=result.success,
                    result_content=result.content if result.success else None,
                    result_error=result.error if not result.success else None,
                )

                self._emit_tool_result(result)

                # Add tool result message
                tool_msg = Message(
                    role="tool",
                    content=result.content if result.success else f"Error: {result.error}",
                    tool_call_id=tool_call_id,
                    name=function_name,
                )
                self.messages.append(tool_msg)

                # Check for cancellation after each tool execution
                if self._check_cancelled():
                    return self._cancel_and_cleanup()

            self._emit_step_footer(step, step_start_time, run_start_time)

            step += 1

        # Max steps reached
        error_msg = f"Task couldn't be completed after {self.max_steps} steps."
        print(f"\n{Colors.BRIGHT_YELLOW}⚠️  {error_msg}{Colors.RESET}")
        return error_msg

    def get_history(self) -> list[Message]:
        """Get message history."""
        return self.messages.copy()
