"""Logging and retry utilities.

Combines two related concerns:
    AgentLogger       — file-based structured run logger (~/.mini-agent/log/)
    async_retry       — exponential-backoff retry decorator with config

Backward-compat re-exports:
    from mini_agent.logger import AgentLogger              # primary
    from mini_agent.retry import RetryConfig, async_retry  # shim → logger
"""
from __future__ import annotations

import asyncio
import functools
import json
import logging as _logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Type, TypeVar

from .schema import Message, ToolCall

logger = _logging.getLogger(__name__)

T = TypeVar("T")


# ---- Agent run logger --------------------------------------------------------
class AgentLogger:
    """Records the complete interaction of each agent run.

    Files written to ~/.mini-agent/log/.
    """

    def __init__(self):
        self.log_dir = Path.home() / ".mini-agent" / "log"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file: Path | None = None
        self.log_index = 0

    def start_new_run(self):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / f"agent_run_{ts}.log"
        self.log_index = 0
        with open(self.log_file, "w", encoding="utf-8") as f:
            f.write("=" * 80 + "\n")
            f.write(f"Agent Run Log - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")

    def log_request(self, messages: list[Message], tools: list[Any] | None = None):
        self.log_index += 1
        req = {"messages": [], "tools": []}
        for msg in messages:
            d = {"role": msg.role, "content": msg.content}
            if msg.thinking:
                d["thinking"] = msg.thinking
            if msg.tool_calls:
                d["tool_calls"] = [tc.model_dump() for tc in msg.tool_calls]
            if msg.tool_call_id:
                d["tool_call_id"] = msg.tool_call_id
            if msg.name:
                d["name"] = msg.name
            req["messages"].append(d)
        if tools:
            req["tools"] = [t.name for t in tools]
        self._write_log("REQUEST", "LLM Request:\n\n" + json.dumps(req, indent=2, ensure_ascii=False))

    def log_response(
        self,
        content: str,
        thinking: str | None = None,
        tool_calls: list[ToolCall] | None = None,
        finish_reason: str | None = None,
    ):
        self.log_index += 1
        d = {"content": content}
        if thinking:
            d["thinking"] = thinking
        if tool_calls:
            d["tool_calls"] = [tc.model_dump() for tc in tool_calls]
        if finish_reason:
            d["finish_reason"] = finish_reason
        self._write_log("RESPONSE", "LLM Response:\n\n" + json.dumps(d, indent=2, ensure_ascii=False))

    def log_tool_result(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result_success: bool,
        result_content: str | None = None,
        result_error: str | None = None,
    ):
        self.log_index += 1
        d = {"tool_name": tool_name, "arguments": arguments, "success": result_success}
        if result_success:
            d["result"] = result_content
        else:
            d["error"] = result_error
        self._write_log("TOOL_RESULT", "Tool Execution:\n\n" + json.dumps(d, indent=2, ensure_ascii=False))

    def _write_log(self, log_type: str, content: str):
        if self.log_file is None:
            return
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write("\n" + "-" * 80 + "\n")
            f.write(f"[{self.log_index}] {log_type}\n")
            f.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}\n")
            f.write("-" * 80 + "\n")
            f.write(content + "\n")

    def get_log_file_path(self) -> Path | None:
        return self.log_file


# ---- Retry decorators --------------------------------------------------------
class RetryConfig:
    """Retry configuration. Plain dataclass-style (not Pydantic).

    Note: config.RetryConfig is the Pydantic version loaded from YAML;
    this is the runtime version used by decorators. They have the same
    fields but different types.
    """

    def __init__(
        self,
        enabled: bool = True,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        retryable_exceptions: tuple[Type[Exception], ...] = (Exception,),
    ):
        self.enabled = enabled
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.retryable_exceptions = retryable_exceptions

    def calculate_delay(self, attempt: int) -> float:
        delay = self.initial_delay * (self.exponential_base**attempt)
        return min(delay, self.max_delay)


class RetryExhaustedError(Exception):
    """Raised when async_retry gives up after max_retries."""

    def __init__(self, last_exception: Exception, attempts: int):
        self.last_exception = last_exception
        self.attempts = attempts
        super().__init__(f"Retry failed after {attempts} attempts. Last error: {last_exception}")


def async_retry(
    config: RetryConfig | None = None,
    on_retry: Callable[[Exception, int], None] | None = None,
) -> Callable:
    """Async function retry decorator with exponential backoff."""
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Exception | None = None
            for attempt in range(config.max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except config.retryable_exceptions as e:
                    last_exception = e
                    if attempt >= config.max_retries:
                        logger.error(
                            f"Function {func.__name__} retry failed, reached maximum retry count {config.max_retries}"
                        )
                        raise RetryExhaustedError(e, attempt + 1)
                    delay = config.calculate_delay(attempt)
                    logger.warning(
                        f"Function {func.__name__} call {attempt + 1} failed: {e}, "
                        f"retrying attempt {attempt + 2} after {delay:.2f} seconds"
                    )
                    if on_retry:
                        on_retry(e, attempt + 1)
                    await asyncio.sleep(delay)
            if last_exception:
                raise last_exception
            raise Exception("Unknown error")

        return wrapper

    return decorator


__all__ = [
    "AgentLogger",
    "RetryConfig",
    "RetryExhaustedError",
    "async_retry",
]
