# Mini-Agent Codebase Refactor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean up dead code, remove shim layers, dedupe repeated code, and refactor oversized functions in Mini-Agent. Production behavior must be unchanged.

**Architecture:** Phase-by-phase removal of dead code (P0), elimination of backward-compat shims by moving callers to canonical paths (P1), structural refactors (P2), and LLM client/config hardening (P3). Each phase ends with passing tests.

**Tech Stack:** Python 3.10+, FastAPI, pytest, prompt-toolkit, anthropic/openai SDKs.

## Global Constraints

- **No behavior changes** — only structural/cleanup. All tests must pass throughout.
- **Run full test suite** at end of each phase: `cd D:\PycharmProjects\Mini-Agent && pytest tests/ -v` (use `.venv` if installed; otherwise install deps first).
- **Commit after each task** with a clear message in the project's existing style: `feat:`, `refactor:`, `chore:`, `fix:`.
- **One commit per task** — never bundle multiple tasks into one commit.
- **Branch safety:** All work happens on `main` branch (user is on main, recent commits are docs-only). User has not asked for a worktree; stay on main.
- **Never force push, never skip hooks, never reset --hard.**
- **Prefer package-level APIs over sub-path imports:** After refactor, all consumers should use `from mini_agent.X import Y` from the canonical home, not from `mini_agent.X.shim`.

---

## Phase 1 (P0) — Remove Dead Code (Zero Risk)

### Task 1: Delete `mini_agent/utils/terminal_utils.py`

**Files:**
- Delete: `mini_agent/utils/terminal_utils.py`
- Verify: `grep -r "terminal_utils" --include="*.py" .` returns nothing

**Background:** Audit confirmed this file has zero importers. `mini_agent.terminal.py` is the canonical home. (The `utils/__init__.py` shim is still used by `cli.py` and 1 test; we'll remove that in Phase 2 Task 11.)

- [ ] **Step 1: Verify no importers**

```bash
cd "D:\PycharmProjects\Mini-Agent" && grep -rn "terminal_utils" --include="*.py" .
```

Expected output: empty (no matches).

- [ ] **Step 2: Delete the file**

```bash
cd "D:\PycharmProjects\Mini-Agent" && rm mini_agent/utils/terminal_utils.py
```

- [ ] **Step 3: Run tests**

```bash
cd "D:\PycharmProjects\Mini-Agent" && .venv/Scripts/python -m pytest tests/ -v 2>&1 | tail -50
```

Expected: All tests pass (this is a NetAppSafe deletion).

- [ ] **Step 4: Commit**

```bash
cd "D:\PycharmProjects\Mini-Agent" && git add -A && git commit -m "chore: remove dead terminal_utils.py shim"
```

---

### Task 2: Delete `mini_agent/core/mcp_client.py`

**Files:**
- Delete: `mini_agent/core/mcp_client.py`

**Background:** Custom HTTP-only MCP client that was never wired up. The actual MCP integration uses `mini_agent/tools/loaders/mcp_loader.py` (the official SDK-based client). Confirmed zero importers via grep.

- [ ] **Step 1: Verify no importers**

```bash
cd "D:\PycharmProjects\Mini-Agent" && grep -rn "from.*mcp_client\|import.*MCPClient\|from.*core.mcp_client" --include="*.py" .
```

Expected: empty.

- [ ] **Step 2: Delete the file**

```bash
cd "D:\PycharmProjects\Mini-Agent" && rm mini_agent/core/mcp_client.py
```

- [ ] **Step 3: Run tests**

```bash
cd "D:\PycharmProjects\Mini-Agent" && .venv/Scripts/python -m pytest tests/ -v 2>&1 | tail -50
```

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
cd "D:\PycharmProjects\Mini-Agent" && git add -A && git commit -m "chore: remove dead core/mcp_client.py (superseded by loaders/mcp_loader.py)"
```

---

### Task 3: Delete `mini_agent/core/sub_agent.py`

**Files:**
- Delete: `mini_agent/core/sub_agent.py`

**Background:** `SubAgent` / `SubAgentTool` are documented as "future use case" in their own docstring. Only referenced in `docs/AGENT_FLOWS.md` (design doc, not code). Confirmed zero code importers.

- [ ] **Step 1: Verify no importers**

```bash
cd "D:\PycharmProjects\Mini-Agent" && grep -rn "SubAgent\|sub_agent" --include="*.py" . | grep -v "sub_agent.py"
```

Expected: empty.

- [ ] **Step 2: Delete the file**

```bash
cd "D:\PycharmProjects\Mini-Agent" && rm mini_agent/core/sub_agent.py
```

- [ ] **Step 3: Run tests**

```bash
cd "D:\PycharmProjects\Mini-Agent" && .venv/Scripts/python -m pytest tests/ -v 2>&1 | tail -50
```

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
cd "D:\PycharmProjects\Mini-Agent" && git add -A && git commit -m "chore: remove dead core/sub_agent.py (unwired future feature)"
```

---

### Task 4: Resolve `schema.py` vs `schema/` ambiguity (delete the single file)

**Files:**
- Delete: `mini_agent/schema.py` (1316 bytes — top-level single file)
- Keep: `mini_agent/schema/__init__.py` (453 bytes — re-export shim that IS active)
- Keep: `mini_agent/schema/schema.py` (1358 bytes — actual definitions)

**Background:** Both `mini_agent/schema.py` and `mini_agent/schema/` directory exist. Python's import system gives precedence to the package directory, so `mini_agent/schema.py` is unreachable. The two files contain near-duplicate class definitions.

**Verification before deletion:** confirm the package directory is what's loaded.

- [ ] **Step 1: Verify `mini_agent/__init__.py` imports from the package**

```bash
cd "D:\PycharmProjects\Mini-Agent" && cat mini_agent/__init__.py
```

Expected: `from .schema import FunctionCall, LLMProvider, LLMResponse, Message, ToolCall` — this resolves to the package directory, not the single file.

- [ ] **Step 2: Delete the single-file `mini_agent/schema.py`**

```bash
cd "D:\PycharmProjects\Mini-Agent" && rm mini_agent/schema.py
```

- [ ] **Step 3: Run tests**

```bash
cd "D:\PycharmProjects\Mini-Agent" && .venv/Scripts/python -m pytest tests/ -v 2>&1 | tail -50
```

Expected: All tests pass. The package directory is what was being loaded all along.

- [ ] **Step 4: Commit**

```bash
cd "D:\PycharmProjects\Mini-Agent" && git add -A && git commit -m "refactor: remove dead top-level schema.py (shadowed by schema/ package)"
```

---

## Phase 2 (P1) — Remove Shim Layers

### Task 5: Migrate `tools/*.py` shim consumers

**Files:**
- Modify: `mini_agent/agent.py:14` — change `from .tools.base import Tool, ToolResult` to `from .tools import Tool, ToolResult`
- Modify: `mini_agent/cli.py:34-38` — change 5 shim imports to package-level imports
- Modify: `mini_agent/tools/__init__.py` — import from canonical paths (`.builtin.X`, `.loaders.X`)
- Modify: `tests/test_acp.py:10` — change `from mini_agent.tools.base` to `from mini_agent.tools`
- Modify: `tests/test_tool_schema.py:7` — same
- Modify: `tests/test_bash_tool.py:7` — change to `from mini_agent.tools.builtin.bash_tool`
- Modify: `tests/test_session_integration.py:14-16` — change to canonical paths
- Modify: `examples/06_tool_schema_demo.py:14` — same

**Background:** Replace shim imports with canonical-path imports. Step 5 establishes the new convention; Step 6 deletes the shim files.

- [ ] **Step 1: Update `mini_agent/tools/__init__.py` to import from canonical paths**

Replace the file contents with:

```python
"""Tools module — canonical public API."""

from .builtin.base import Tool, ToolResult
from .builtin.bash_tool import BashTool
from .builtin.file_tools import EditTool, ReadTool, WriteTool
from .builtin.note_tool import RecallNoteTool, SessionNoteTool

__all__ = [
    "Tool",
    "ToolResult",
    "ReadTool",
    "WriteTool",
    "EditTool",
    "BashTool",
    "SessionNoteTool",
    "RecallNoteTool",
]
```

- [ ] **Step 2: Update `mini_agent/agent.py` line 14**

Change `from .tools.base import Tool, ToolResult` to `from .tools import Tool, ToolResult`.

- [ ] **Step 3: Update `mini_agent/cli.py` lines 34-38**

Replace these 5 lines:
```python
from mini_agent.tools.base import Tool
from mini_agent.tools.bash_tool import BashKillTool, BashOutputTool, BashTool
from mini_agent.tools.file_tools import EditTool, ReadTool, WriteTool
from mini_agent.tools.mcp_loader import cleanup_mcp_connections, load_mcp_tools_async, set_mcp_timeout_config
from mini_agent.tools.note_tool import SessionNoteTool
```

With:
```python
from mini_agent.tools import BashTool, EditTool, ReadTool, SessionNoteTool, Tool, WriteTool
from mini_agent.tools.loaders.mcp_loader import (
    cleanup_mcp_connections,
    load_mcp_tools_async,
    set_mcp_timeout_config,
)
from mini_agent.tools.builtin.bash_tool import BashKillTool, BashOutputTool
```

- [ ] **Step 4: Update test files**

For each of these replace the shim import with the canonical path:
- `tests/test_acp.py:10` — `from mini_agent.tools.base import Tool, ToolResult` → `from mini_agent.tools import Tool, ToolResult`
- `tests/test_tool_schema.py:7` — same
- `tests/test_bash_tool.py:7` — `from mini_agent.tools.bash_tool import BashTool` → `from mini_agent.tools.builtin.bash_tool import BashTool`
- `tests/test_session_integration.py:14-16` — change all 3 shim imports to canonical paths
- `examples/06_tool_schema_demo.py:14` — `from mini_agent.tools.base import Tool` → `from mini_agent.tools import Tool`

Check each file before editing to confirm the exact line.

- [ ] **Step 5: Run tests**

```bash
cd "D:\PycharmProjects\Mini-Agent" && .venv/Scripts/python -m pytest tests/ -v 2>&1 | tail -50
```

Expected: All tests still pass.

- [ ] **Step 6: Commit**

```bash
cd "D:\PycharmProjects\Mini-Agent" && git add -A && git commit -m "refactor: migrate consumers off tools/*.py shims to canonical paths"
```

---

### Task 6: Delete `mini_agent/tools/*.py` shim files

**Files:**
- Delete: `mini_agent/tools/base.py`
- Delete: `mini_agent/tools/bash_tool.py`
- Delete: `mini_agent/tools/file_tools.py`
- Delete: `mini_agent/tools/note_tool.py`
- Delete: `mini_agent/tools/mcp_loader.py`

**Background:** After Task 5, these shim files have no remaining consumers. The empty `tools/builtin/__init__.py` and `tools/loaders/__init__.py` stay (they're package markers).

- [ ] **Step 1: Verify no remaining importers**

```bash
cd "D:\PycharmProjects\Mini-Agent" && grep -rn "from mini_agent.tools.base\|from mini_agent.tools.bash_tool\|from mini_agent.tools.file_tools\|from mini_agent.tools.note_tool\|from mini_agent.tools.mcp_loader\|from .tools.base\|from .tools.bash_tool\|from .tools.file_tools\|from .tools.note_tool\|from .tools.mcp_loader" --include="*.py" .
```

Expected: empty.

- [ ] **Step 2: Delete the 5 shim files**

```bash
cd "D:\PycharmProjects\Mini-Agent" && rm mini_agent/tools/base.py mini_agent/tools/bash_tool.py mini_agent/tools/file_tools.py mini_agent/tools/note_tool.py mini_agent/tools/mcp_loader.py
```

- [ ] **Step 3: Run tests**

```bash
cd "D:\PycharmProjects\Mini-Agent" && .venv/Scripts/python -m pytest tests/ -v 2>&1 | tail -50
```

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
cd "D:\PycharmProjects\Mini-Agent" && git add -A && git commit -m "refactor: delete tools/*.py shim files (canonical paths in builtin/ and loaders/)"
```

---

### Task 7: Migrate `retry.py` shim consumers

**Files:**
- Modify: `mini_agent/cli.py:536` — find `from .retry import ...` (or similar) and change to `from .logger import RetryConfig as RetryConfigBase`
- Modify: `mini_agent/acp/__init__.py:38` — change `from mini_agent.retry import RetryConfig as RetryConfigBase` to `from mini_agent.logger import RetryConfig as RetryConfigBase`
- Modify: `tests/test_llm_clients.py:14` — change `from mini_agent.retry import X` to `from mini_agent.logger import X`

- [ ] **Step 1: Find all imports of `mini_agent.retry`**

```bash
cd "D:\PycharmProjects\Mini-Agent" && grep -rn "from mini_agent.retry\|from .retry" --include="*.py" .
```

Expected output — 3 hits as listed above.

- [ ] **Step 2: Update each consumer**

For each of the 3 files, replace `from mini_agent.retry(...)` → `from mini_agent.logger(...)` (preserving the `as RetryConfigBase` alias if used).

- [ ] **Step 3: Run tests**

```bash
cd "D:\PycharmProjects\Mini-Agent" && .venv/Scripts/python -m pytest tests/ -v 2>&1 | tail -50
```

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
cd "D:\PycharmProjects\Mini-Agent" && git add -A && git commit -m "refactor: migrate consumers off mini_agent.retry shim"
```

---

### Task 8: Delete `mini_agent/retry.py`

**Files:**
- Delete: `mini_agent/retry.py`

- [ ] **Step 1: Verify no remaining importers**

```bash
cd "D:\PycharmProjects\Mini-Agent" && grep -rn "from mini_agent.retry\|from .retry\|import mini_agent.retry" --include="*.py" .
```

Expected: empty.

- [ ] **Step 2: Delete the file**

```bash
cd "D:\PycharmProjects\Mini-Agent" && rm mini_agent/retry.py
```

- [ ] **Step 3: Run tests**

```bash
cd "D:\PycharmProjects\Mini-Agent" && .venv/Scripts/python -m pytest tests/ -v 2>&1 | tail -50
```

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
cd "D:\PycharmProjects\Mini-Agent" && git add -A && git commit -m "refactor: delete mini_agent/retry.py shim"
```

---

### Task 9: Migrate `data_agent/` shim consumers

**Files:**
- Modify: `mini_agent/api/deps.py:16-21` — replace `from mini_agent.data_agent import (...)` with direct imports from `connectors`, `memory`, `render`
- Modify: `mini_agent/api/routes.py:24` — replace `from mini_agent.data_agent import SessionStore` with `from mini_agent.memory.session import SessionStore`
- Modify: `tests/test_sqlbot_client.py:9` — replace shim import with direct imports

**Background:** `mini_agent.data_agent` is marked "Deprecated shim" in its own docstring. The canonical homes are:
- `mini_agent.connectors.sqlbot` (SqlBotClient, SqlBotConfig, SqlBotError, SqlBotAuthError, SqlBotTransientError, decode_sql_b64, parse_data_envelope)
- `mini_agent.memory.session` (Message, Session, SessionStore)
- `mini_agent.render` (render_answer_md, render_from_data_envelope, render_markdown_table, describe_chart, download_chart)

- [ ] **Step 1: Find all imports of `mini_agent.data_agent`**

```bash
cd "D:\PycharmProjects\Mini-Agent" && grep -rn "from mini_agent.data_agent\|from .data_agent" --include="*.py" .
```

Expected output — 3 hits: `api/deps.py`, `api/routes.py`, `tests/test_sqlbot_client.py`.

- [ ] **Step 2: Update `mini_agent/api/deps.py`**

Replace:
```python
from mini_agent.data_agent import (
    SessionStore,
    SqlBotClient,
    decode_sql_b64,
    render_answer_md,
)
```

With:
```python
from mini_agent.connectors.sqlbot import SqlBotClient, decode_sql_b64
from mini_agent.memory.session import SessionStore
from mini_agent.render import render_answer_md
```

- [ ] **Step 3: Update `mini_agent/api/routes.py`**

Replace `from mini_agent.data_agent import SessionStore` with `from mini_agent.memory.session import SessionStore`.

- [ ] **Step 4: Update `tests/test_sqlbot_client.py`**

Read the file's imports section to see what's used, then replace each `from mini_agent.data_agent import X` with the canonical-source import:
- `SqlBotClient, SqlBotConfig, ...` → `from mini_agent.connectors.sqlbot import ...`
- `SessionStore, Session, Message` → `from mini_agent.memory.session import ...`
- `render_answer_md, ...` → `from mini_agent.render import ...`

- [ ] **Step 5: Run tests**

```bash
cd "D:\PycharmProjects\Mini-Agent" && .venv/Scripts/python -m pytest tests/ -v 2>&1 | tail -50
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
cd "D:\PycharmProjects\Mini-Agent" && git add -A && git commit -m "refactor: migrate consumers off mini_agent.data_agent shim"
```

---

### Task 10: Delete `mini_agent/data_agent/` directory

**Files:**
- Delete: `mini_agent/data_agent/__init__.py`
- Delete: `mini_agent/data_agent/` directory (recursively)

- [ ] **Step 1: Verify no remaining importers**

```bash
cd "D:\PycharmProjects\Mini-Agent" && grep -rn "from mini_agent.data_agent\|from .data_agent\|import mini_agent.data_agent" --include="*.py" .
```

Expected: empty.

- [ ] **Step 2: Delete the directory**

```bash
cd "D:\PycharmProjects\Mini-Agent" && rm -rf mini_agent/data_agent/
```

- [ ] **Step 3: Run tests**

```bash
cd "D:\PycharmProjects\Mini-Agent" && .venv/Scripts/python -m pytest tests/ -v 2>&1 | tail -50
```

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
cd "D:\PycharmProjects\Mini-Agent" && git add -A && git commit -m "refactor: delete deprecated mini_agent/data_agent/ shim"
```

---

### Task 11: Migrate `utils/__init__.py` consumers

**Files:**
- Modify: `mini_agent/agent.py:15` — change `from .utils import calculate_display_width` to `from .terminal import calculate_display_width`
- Modify: `mini_agent/cli.py:39` — change `from mini_agent.utils import calculate_display_width` to `from mini_agent.terminal import calculate_display_width`
- Modify: `tests/test_terminal_utils.py:5` — same

- [ ] **Step 1: Update `mini_agent/agent.py` line 15**

Change `from .utils import calculate_display_width` to `from .terminal import calculate_display_width`.

- [ ] **Step 2: Update `mini_agent/cli.py` line 39**

Change `from mini_agent.utils import calculate_display_width` to `from mini_agent.terminal import calculate_display_width`.

- [ ] **Step 3: Update `tests/test_terminal_utils.py` line 5**

Change `from mini_agent.utils import (calculate_display_width, pad_to_width, truncate_with_ellipsis)` to `from mini_agent.terminal import (calculate_display_width, pad_to_width, truncate_with_ellipsis)`.

Also consider renaming the test file to `test_terminal.py` to match the module name (optional, but consistent).

- [ ] **Step 4: Run tests**

```bash
cd "D:\PycharmProjects\Mini-Agent" && .venv/Scripts/python -m pytest tests/ -v 2>&1 | tail -50
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
cd "D:\PycharmProjects\Mini-Agent" && git add -A && git commit -m "refactor: migrate consumers off mini_agent.utils shim to terminal module"
```

---

### Task 12: Delete `mini_agent/utils/` directory

**Files:**
- Delete: `mini_agent/utils/__init__.py`
- Delete: `mini_agent/utils/` directory (already partially empty after Task 1)

- [ ] **Step 1: Verify no remaining importers**

```bash
cd "D:\PycharmProjects\Mini-Agent" && grep -rn "from mini_agent.utils\|from .utils\|import mini_agent.utils" --include="*.py" .
```

Expected: empty.

- [ ] **Step 2: Delete the directory**

```bash
cd "D:\PycharmProjects\Mini-Agent" && rm -rf mini_agent/utils/
```

- [ ] **Step 3: Run tests**

```bash
cd "D:\PycharmProjects\Mini-Agent" && .venv/Scripts/python -m pytest tests/ -v 2>&1 | tail -50
```

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
cd "D:\PycharmProjects\Mini-Agent" && git add -A && git commit -m "refactor: delete mini_agent/utils/ shim directory"
```

---

### Task 13: Merge duplicated `Colors` class into `mini_agent/terminal.py`

**Files:**
- Modify: `mini_agent/terminal.py` — add `Colors` class with the union of both definitions
- Modify: `mini_agent/agent.py:20-43` — remove inline `Colors` class, import from `terminal`
- Modify: `mini_agent/cli.py:44-76` — remove inline `Colors` class, import from `terminal`

**Background:** `Colors` class is fully duplicated between `agent.py:20-43` (19 members) and `cli.py:44-76` (24 members — adds BLACK, WHITE, BG_BLACK, BG_RED, BG_GREEN, BG_BLUE). The canonical home is `mini_agent/terminal.py` (where every other display-related helper lives).

- [ ] **Step 1: Append `Colors` class to `mini_agent/terminal.py`**

Add at the end of the file (after `pad_to_width`):

```python
class Colors:
    """ANSI color codes for terminal output.

    Union of historical Colors classes from agent.py and cli.py.
    The richer set (with BG_* and unused colors) is kept verbatim;
    unused members are not pruned to avoid risk of breaking callers.
    """

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Foreground colors
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Bright colors
    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"

    # Background colors
    BG_BLACK = "\033[40m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_BLUE = "\033[44m"
```

Also update `__all__` to include `"Colors"`.

- [ ] **Step 2: Remove `Colors` from `mini_agent/agent.py`**

- Delete lines 19-43 (the class definition).
- Add `from .terminal import Colors` near the top (after the existing `from .terminal import calculate_display_width` change from Task 11).

- [ ] **Step 3: Remove `Colors` from `mini_agent/cli.py`**

- Delete lines 43-76 (the class definition).
- Add `from mini_agent.terminal import Colors` in the imports section.

- [ ] **Step 4: Run tests**

```bash
cd "D:\PycharmProjects\Mini-Agent" && .venv/Scripts/python -m pytest tests/ -v 2>&1 | tail -50
```

Expected: All tests pass.

- [ ] **Step 5: Run smoke check — do `agent.py` and `cli.py` still reference `Colors` correctly?**

```bash
cd "D:\PycharmProjects\Mini-Agent" && .venv/Scripts/python -c "from mini_agent.terminal import Colors; print(Colors.RED, Colors.BG_RED)"
```

Expected: prints two ANSI escape codes.

- [ ] **Step 6: Commit**

```bash
cd "D:\PycharmProjects\Mini-Agent" && git add -A && git commit -m "refactor: consolidate Colors class into mini_agent.terminal"
```

---

## Phase 3 (P2) — Structure Refactors

### Task 14: Unify `RetryConfig` (drop Pydantic duplicate)

**Files:**
- Modify: `mini_agent/config.py` — remove the Pydantic `RetryConfig` class, import the dataclass version from `logger`

**Background:** Two `RetryConfig` definitions exist today:
- `mini_agent/config.py:12` — `RetryConfig(BaseModel)` with `enabled/max_retries/initial_delay/max_delay/exponential_base`. Used only by `from_yaml()`.
- `mini_agent/logger.py:116` — `RetryConfig` dataclass. Used by LLM clients at runtime.

`cli.py:536-546` manually copies fields between the two. This is the source of "drift" risk.

**Unify on the dataclass version** (from `logger.py`) since that's what the LLM clients actually consume.

- [ ] **Step 1: Inspect the dataclass `RetryConfig` in `mini_agent/logger.py`**

```bash
cd "D:\PycharmProjects\Mini-Agent" && grep -n "class RetryConfig" mini_agent/logger.py
```

Read the dataclass to confirm it has the same fields: `enabled`, `max_retries`, `initial_delay`, `max_delay`, `exponential_base`.

- [ ] **Step 2: Replace the Pydantic `RetryConfig` in `mini_agent/config.py`**

In `config.py`:
- Delete the `RetryConfig` class (lines 12-20).
- Add `from .logger import RetryConfig` at the top.
- Update `LLMConfig.retry: RetryConfig = Field(default_factory=RetryConfig)` — since dataclasses don't accept `Field(default_factory=...)`, change to `retry: RetryConfig = None` and handle in `__init__`, OR use a different approach.

**Recommended approach:** Keep `LLMConfig` as a Pydantic model but import `RetryConfig` from `logger`. Modify `LLMConfig.retry` to be a `RetryConfig | None = None` type, and resolve the default in `from_yaml()`.

Alternative (simpler): change `LLMConfig` from `BaseModel` to `@dataclass`, but this expands the scope. Stick with the first approach.

- [ ] **Step 3: Update `from_yaml()` to construct the dataclass `RetryConfig` directly**

Replace the retry parsing block (lines 113-121):

```python
retry_data = data.get("retry", {})
retry_config = RetryConfig(
    enabled=retry_data.get("enabled", True),
    max_retries=retry_data.get("max_retries", 3),
    initial_delay=retry_data.get("initial_delay", 1.0),
    max_delay=retry_data.get("max_delay", 60.0),
    exponential_base=retry_data.get("exponential_base", 2.0),
)
```

This already constructs the dataclass version (since `RetryConfig` in the module scope is now the dataclass). Confirm by re-reading.

- [ ] **Step 4: Run tests**

```bash
cd "D:\PycharmProjects\Mini-Agent" && .venv/Scripts/python -m pytest tests/ -v 2>&1 | tail -50
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
cd "D:\PycharmProjects\Mini-Agent" && git add -A && git commit -m "refactor: unify RetryConfig on dataclass version (drop Pydantic duplicate)"
```

---

### Task 15: Fix YAML flat vs model nested mismatch

**Files:**
- Modify: `mini_agent/config.py` — keep `from_yaml()` flat-parsing but ensure all fields are surfaced. Add `BOX_WIDTH`-style fields to `AgentConfig` so magic numbers are tunable.

**Background:** `config-example.yaml` has flat top-level keys (`api_key`, `max_steps`, `workspace_dir`), but Pydantic models are nested (`llm.api_key`, `agent.max_steps`). `from_yaml()` manually bridges with ~80 lines. Choose to keep the YAML flat (user-friendly) and improve the parsing; do not restructure to nested.

The actual change here is modest: explicitly pass all fields through, add the missing boxes/limits to `AgentConfig` so users can tune them.

- [ ] **Step 1: Read current `config-example.yaml`**

```bash
cd "D:\PycharmProjects\Mini-Agent" && cat mini_agent/config/config-example.yaml
```

List all fields the example declares.

- [ ] **Step 2: Identify any fields in the example that are NOT surfaced in Pydantic models**

Cross-reference. The audit already noted `BOX_WIDTH`, `max_tokens`, `token_limit`, display truncation limits are hardcoded and not in config-example. Add the most impactful ones:

- `max_steps` (already present)
- `token_limit` (default 80000 in agent.py:56) → add to `AgentConfig`
- `box_width` (default 58 in agent.py:453) → add to `AgentConfig`

- [ ] **Step 3: Extend `AgentConfig` with tunable fields**

In `mini_agent/config.py`, add:

```python
class AgentConfig(BaseModel):
    max_steps: int = 50
    workspace_dir: str = "./workspace"
    system_prompt_path: str = "system_prompt.md"
    token_limit: int = 80000  # Summary triggered when tokens exceed this value
    box_width: int = 58      # Terminal box display width
```

- [ ] **Step 4: Update `from_yaml()` to pass these fields**

Update `agent_config = AgentConfig(...)` (lines 132-136) to read from YAML:

```python
agent_config = AgentConfig(
    max_steps=data.get("max_steps", 50),
    workspace_dir=data.get("workspace_dir", "./workspace"),
    system_prompt_path=data.get("system_prompt_path", "system_prompt.md"),
    token_limit=data.get("token_limit", 80000),
    box_width=data.get("box_width", 58),
)
```

- [ ] **Step 5: Update `config-example.yaml` to document the new fields**

Add commented examples:

```yaml
# token_limit: 80000     # Token threshold for context summarization
# box_width: 58          # Terminal box width for step display
```

- [ ] **Step 6: Run tests**

```bash
cd "D:\PycharmProjects\Mini-Agent" && .venv/Scripts/python -m pytest tests/ -v 2>&1 | tail -50
```

Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
cd "D:\PycharmProjects\Mini-Agent" && git add -A && git commit -m "refactor: surface token_limit and box_width in config"
```

---

### Task 16: Split `Agent.run()` into smaller methods

**Files:**
- Modify: `mini_agent/agent.py` — extract helper methods from `Agent.run()` (lines ~418-616)

**Background:** `Agent.run()` is ~200 lines with 7+ responsibilities. Goal: keep the public API stable (`run(message: str) -> str`) but split the body into private helper methods.

**Suggested decomposition:**
- `_maybe_summarize(messages)` — already exists or move into a helper
- `_emit_step_header(step_idx, description)` — print the box-drawing header
- `_emit_tool_call(tool_call)` — print argument truncation
- `_emit_tool_result(tool_name, result, elapsed)` — print result preview
- `_execute_one_tool(tool_call) -> ToolResult` — wraps single tool execution with exception handling
- `_chat_with_tools(messages)` — single LLM round, returns response
- `run()` — the orchestrator, much shorter

**Behavior must be preserved exactly.** This is structural only.

- [ ] **Step 1: Read the current `run()` method to understand its full structure**

```bash
cd "D:\PycharmProjects\Mini-Agent" && grep -n "def run\b\|def execute_tool\|def _summarize" mini_agent/agent.py
```

Expected: `run`, `execute_tool`, and possibly `_summarize_messages`.

- [ ] **Step 2: Extract `_emit_step_header`**

Create a method that prints the box-drawing header. Move the appropriate lines from `run()`. Check the cancellation event check is preserved.

- [ ] **Step 3: Extract `_emit_tool_call` and `_emit_tool_result`**

Move the argument/result printing logic out of `run()`. Verify the truncation lengths (200/300) are preserved.

- [ ] **Step 4: Extract `_execute_one_tool`**

Use the existing `Agent.execute_tool()` method (line 136) which already does the right thing. Modify `run()` to call it instead of inlining the try/except.

- [ ] **Step 5: Refactor `run()` to compose the helpers**

Target: `run()` should be ~50 lines, readable top-to-bottom as:
1. Print "started"
2. While step < max_steps and not cancelled:
   a. _maybe_summarize
   b. response = _chat_with_tools
   c. if no tool calls: return
   d. _emit_step_header
   e. for each tool_call: emit + execute + emit result
3. Print "done"

- [ ] **Step 6: Run tests**

```bash
cd "D:\PycharmProjects\Mini-Agent" && .venv/Scripts/python -m pytest tests/ -v 2>&1 | tail -50
```

Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
cd "D:\PycharmProjects\Mini-Agent" && git add -A && git commit -m "refactor: split Agent.run() into focused helper methods"
```

---

### Task 17: Split `cli.py:run_agent()` into smaller functions

**Files:**
- Modify: `mini_agent/cli.py` — extract `setup_agent()`, `setup_prompt_session()`, `handle_command()`, `esc_key_listener()` (already a helper)

**Background:** `run_agent()` is ~345 lines. The platform-specific Esc key listener is especially out of place.

**Suggested decomposition:**
- `_build_agent(config) -> Agent` — config + LLM + tools + plugins + system prompt
- `_setup_prompt_session(workspace_dir, history_path) -> PromptSession` — all the prompt_toolkit wiring
- `_esc_key_listener_task(cancel_event) -> asyncio.Task` — extract the inner closure, move to module level so it can be tested
- `_handle_command(cmd: str, agent, ...) -> bool` — command dispatch loop
- `run_agent()` — orchestrates the above

- [ ] **Step 1: Extract `_build_agent()`**

Move the LLM client construction, retry config wiring, base tools, MCP loading, workspace tools, and system prompt loading into one function.

- [ ] **Step 2: Extract `_setup_prompt_session()`**

Move the prompt_toolkit session creation (history, completion, keybindings, style) into one function.

- [ ] **Step 3: Extract `_esc_key_listener()` as a module-level async function**

Move the platform-specific msvcrt/termios code out of the inline closure. Keep Windows and Unix branches but in a single function.

- [ ] **Step 4: Extract `_handle_command()`**

Move the command dispatch (10+ commands) into a separate function that returns a bool indicating "exit".

- [ ] **Step 5: Trim `run_agent()` to the orchestrator**

Target: `run_agent()` is ~50 lines of clear orchestration.

- [ ] **Step 6: Run tests**

```bash
cd "D:\PycharmProjects\Mini-Agent" && .venv/Scripts/python -m pytest tests/ -v 2>&1 | tail -50
```

Expected: All tests pass.

- [ ] **Step 7: Smoke test — try `python -m mini_agent.cli --help`**

```bash
cd "D:\PycharmProjects\Mini-Agent" && .venv/Scripts/python -m mini_agent.cli --help
```

Expected: Help output appears (this confirms imports/syntax are valid).

- [ ] **Step 8: Commit**

```bash
cd "D:\PycharmProjects\Mini-Agent" && git add -A && git commit -m "refactor: split cli.py run_agent() into focused setup/run/handler functions"
```

---

## Phase 4 (P3) — LLM Client & Magic Numbers

### Task 18: Extract `generate()` template method to base

**Files:**
- Modify: `mini_agent/llm/base.py` — add a `_make_api_request()` and `_parse_response()` template in `generate()`
- Modify: `mini_agent/llm/anthropic_client.py` — remove logic from `generate()` that lives in the base
- Modify: `mini_agent/llm/openai_client.py` — same

**Background:** Both `AnthropicClient.generate()` and `OpenAIClient.generate()` share a 5-step flow:
```
_prepare_request() → if retry enabled: wrap → _make_api_request() → _parse_response()
```

The `_make_api_request()` signatures differ (Anthropic takes system_message separately, OpenAI embeds in messages). Unify by always returning `(system_message, api_messages)` from a helper, then have `_make_api_request((system, msgs), tools)`.

**Note:** This task is the most behavior-sensitive. The structure has been left intentionally optional; if the unified method proves too complex, leave the duplication and just deduplicate the retry wrapping step.

- [ ] **Step 1: Read both `generate()` methods side by side**

```bash
cd "D:\PycharmProjects\Mini-Agent" && grep -n "def generate\|def _make_api_request\|def _parse_response\|def _prepare_request\|def _convert" mini_agent/llm/anthropic_client.py mini_agent/llm/openai_client.py mini_agent/llm/base.py
```

- [ ] **Step 2: Add the template method to `LLMClientBase`**

In `mini_agent/llm/base.py`, add a `generate()` skeleton that:
- Calls `_prepare_request()`
- Calls `_make_api_request()` with retry wrapping if enabled
- Calls `_parse_response()`

Keep both subclass `generate()` methods valid by having them call the base method.

- [ ] **Step 3: Hoist the retry wrapping into the base**

The `if self.retry_config.enabled: ...` block is duplicated. Move it into the base so subclasses don't need to repeat it.

- [ ] **Step 4: Unify `(_make_api_request)` signatures**

Option: introduce a `_convert_messages()` helper that returns `(system_message, api_messages)` consistently. Then `_make_api_request((system, msgs), tools)` has the same signature for both providers.

- [ ] **Step 5: Run tests**

```bash
cd "D:\PycharmProjects\Mini-Agent" && .venv/Scripts/python -m pytest tests/ -v 2>&1 | tail -50
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
cd "D:\PycharmProjects\Mini-Agent" && git add -A && git commit -m "refactor: unify LLM client generate() flow with template method in base"
```

---

### Task 19: Move hardcoded magic numbers to config

**Files:**
- Modify: `mini_agent/agent.py` — read `box_width` from config (already done in Task 15 for `AgentConfig`); add `token_limit` and `tool_arg_truncate_len` and `tool_result_truncate_len` to `AgentConfig`
- Modify: `mini_agent/config.py` — add new fields to `AgentConfig`
- Modify: `mini_agent/config/config-example.yaml` — document the new fields

**Background:** Audit found:
- `agent.py:543` `if len(value_str) > 200` — argument truncation
- `agent.py:585-587` `if len(result_text) > 300` — result truncation
- `anthropic_client.py:69` `max_tokens: 16384` — LLM max output

The first two can be configurable; the third is a per-model concern and should stay in the LLM client.

- [ ] **Step 1: Add the new fields to `AgentConfig`**

```python
class AgentConfig(BaseModel):
    max_steps: int = 50
    workspace_dir: str = "./workspace"
    system_prompt_path: str = "system_prompt.md"
    token_limit: int = 80000
    box_width: int = 58
    tool_arg_truncate_len: int = 200   # Truncate tool args longer than this in display
    tool_result_truncate_len: int = 300  # Truncate tool results longer than this in display
```

- [ ] **Step 2: Update `from_yaml()` to read these**

```python
agent_config = AgentConfig(
    max_steps=data.get("max_steps", 50),
    workspace_dir=data.get("workspace_dir", "./workspace"),
    system_prompt_path=data.get("system_prompt_path", "system_prompt.md"),
    token_limit=data.get("token_limit", 80000),
    box_width=data.get("box_width", 58),
    tool_arg_truncate_len=data.get("tool_arg_truncate_len", 200),
    tool_result_truncate_len=data.get("tool_result_truncate_len", 300),
)
```

- [ ] **Step 3: Pass `AgentConfig` to `Agent.__init__` and use it**

In `mini_agent/cli.py`, where `Agent(...)` is built, pass `token_limit=cfg.agent.token_limit`, and use `cfg.agent.box_width`, `cfg.agent.tool_arg_truncate_len`, `cfg.agent.tool_result_truncate_len` throughout the CLI display path.

In `mini_agent/agent.py`, use `self.box_width`, `self.tool_arg_truncate_len`, `self.tool_result_truncate_len` instead of the hardcoded literals.

- [ ] **Step 4: Update `config-example.yaml`**

```yaml
# token_limit: 80000
# box_width: 58
# tool_arg_truncate_len: 200
# tool_result_truncate_len: 300
```

- [ ] **Step 5: Run tests**

```bash
cd "D:\PycharmProjects\Mini-Agent" && .venv/Scripts/python -m pytest tests/ -v 2>&1 | tail -50
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
cd "D:\PycharmProjects\Mini-Agent" && git add -A && git commit -m "refactor: surface tool arg/result truncation limits in config"
```

---

## Self-Review (writer's checklist)

**Spec coverage:** Each finding from the original audit is addressed:
- Dead code (3 files) → Phase 1 Tasks 1, 2, 3
- Schema ambiguity → Phase 1 Task 4
- `tools/*.py` shims → Phase 2 Tasks 5, 6
- `retry.py` shim → Phase 2 Tasks 7, 8
- `data_agent/` shim → Phase 2 Tasks 9, 10
- `utils/__init__.py` shim → Phase 2 Tasks 11, 12
- `Colors` duplication → Phase 2 Task 13
- `RetryConfig` duplicate → Phase 3 Task 14
- YAML/model mismatch → Phase 3 Task 15
- `Agent.run()` monolith → Phase 3 Task 16
- `run_agent()` monolith → Phase 3 Task 17
- LLM client duplication → Phase 4 Task 18
- Hardcoded magic numbers → Phase 3 Task 15 + Phase 4 Task 19

**Open items not addressed (intentional):**
- `BackgroundShellManager` class-level global state (out of scope; risky refactor)
- `agent.py:120` docstring says "two execution paths exist" (documentation only)
- `cli.py:556` provider string validation (small, isolated fix; can be done in a follow-up)
- `llm_wrapper.py:58` `self.retry_config` inconsistency (small; can be done in a follow-up)
- `web/package-lock.json` Next.js version (not Python code; not in scope)

**Placeholder scan:** No "TBD", "TODO", "implement later", etc. All steps have concrete commands or code.

**Type consistency:** `Colors` is the same name in terminal.py and all callers. `RetryConfig` is the same dataclass everywhere. `Tool`, `ToolResult`, `BashTool`, etc. are imported from canonical paths consistently.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-08-03-mini-agent-refactor.md`. Two execution options:**

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?** Default to subagent-driven since this is a 19-task refactor with discrete, parallelizable units.

If subagent-driven, I will:
- For each task, dispatch a fresh subagent with the exact task content
- The subagent edits files, runs tests, commits, and reports back
- I review the diff and approve before moving to the next task

If inline:
- I execute tasks sequentially in this session
- I run full test suite after each phase
- I commit at the end of each task

Note: phases depend on each other (Phase 2 must follow Phase 1 for safety; Phases 3-4 require Phase 2 complete). Within a phase, tasks should be sequential (each task builds on the previous one's commits).
