"""Plugins - unified registry for Tools, MCP servers, and Skills.

Three extension types, one entry point:

1. **Tools** - atomic actions (Python class extending Tool)
   Add: create a class in tools/, auto-discovered or register_tool()

2. **MCP** - external MCP servers (HTTP/SSE/stdio)
   Add: edit mcp.json, auto-loaded at startup

3. **Skills** - Anthropic-style folders (SKILL.md + scripts/)
   Add: create folder under skills/, auto-discovered

All three contribute tools to Plugins.all_tools() and prompts to system_prompt_addition().
"""
from __future__ import annotations

import importlib
import inspect
import logging
from pathlib import Path
from typing import Any

from ..tools.base import Tool, ToolResult
from .skill import Skill, SkillManager, load_skill

logger = logging.getLogger(__name__)


class _SkillRunnerTool(Tool):
    """Wraps Skills as a single `run_skill(skill_name, input)` Tool."""

    def __init__(self, plugins: "Plugins"):
        self._plugins = plugins

    @property
    def name(self) -> str:
        return "run_skill"

    @property
    def description(self) -> str:
        names = self._plugins.skill_names()
        return (
            f"运行一个 Skill。可用 Skills: {', '.join(names)}. "
            "调用后返回该 Skill 的完整指令（SKILL.md），你需按指令执行后续步骤。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": f"Skill 名（可选: {', '.join(self._plugins.skill_names())}）",
                },
                "input": {
                    "type": "string",
                    "description": "用户输入或问题",
                },
            },
            "required": ["skill_name", "input"],
        }

    async def execute(self, *, skill_name: str, input: str, **kwargs) -> ToolResult:
        skill = self._plugins.get_skill(skill_name)
        if not skill:
            return ToolResult(
                success=False,
                error=f"Skill not found: {skill_name}. Available: {self._plugins.skill_names()}",
            )
        scripts = skill.list_scripts()
        scripts_section = "\n".join(f"- {s.name}" for s in scripts) if scripts else "(none)"
        content = (
            f"# Skill: {skill.name}\n\n"
            f"**Skill Root Directory:** `{skill.folder}`\n\n"
            f"## Instructions\n{skill.instructions}\n\n"
            f"## User Input\n{input}\n\n"
            f"## Available Scripts\n{scripts_section}\n"
        )
        return ToolResult(success=True, content=content)


class Plugins:
    """Unified registry: Tools + MCP + Skills.

    Usage:
        plugins = Plugins(skills_dirs=["./skills", "mini_agent/skills"])
        plugins.discover_tools("mini_agent/tools")
        await plugins.load_mcp_servers()
        plugins.discover_skills()

        agent = Agent(llm=..., system_prompt=..., plugins=plugins)
        print(plugins.stats())  # {'tools': 5, 'mcp_tools': 6, 'skills': 1, 'total': 12}
    """

    def __init__(
        self,
        skills_dirs: list[str | Path] | None = None,
        workspace_dir: str | Path = "./workspace",
    ):
        # Multi-path skills search (priority: higher index = lower priority)
        self._skills_dirs = [Path(d).expanduser() for d in (skills_dirs or ["./skills"])]
        self._workspace_dir = Path(workspace_dir)
        self._tools: list[Tool] = []
        self._mcp_tools: list[Tool] = []
        self._skill_manager = SkillManager(self._skills_dirs)
        self._mcp_loaded = False

    # -------- Tools (atomic Python actions) --------

    def register_tool(self, tool: Tool) -> None:
        """Register a single Tool."""
        # Inject resources if Tool supports it
        if hasattr(tool, "bind_resources"):
            try:
                tool.bind_resources(workspace_dir=self._workspace_dir)
            except Exception as e:
                logger.warning(f"bind_resources failed for {tool.name}: {e}")
        self._tools.append(tool)
        logger.info(f"registered tool: {tool.name}")

    def register_tools(self, tools: list[Tool]) -> None:
        """Register multiple Tools at once."""
        for t in tools:
            self.register_tool(t)

    def discover_tools(self, tools_dir: str | Path) -> int:
        """Auto-scan a directory (recursively) for Tool subclasses.

        Convention: each *.py (not starting with _) is imported; all public
        Tool subclasses are instantiated and registered. Recurses into
        subdirectories so layout splits like ``tools/builtin/`` and
        ``tools/loaders/`` are discovered transparently.

        Returns: number of tools registered.
        """
        tools_dir = Path(tools_dir)
        if not tools_dir.exists():
            logger.info(f"tools dir not found: {tools_dir}")
            return 0

        # Determine module path prefix
        # e.g. mini_agent/tools/ -> module "mini_agent.tools"
        module_prefix = self._infer_module_prefix(tools_dir)

        count_before = len(self._tools)
        for py_file in sorted(tools_dir.rglob("*.py")):
            if py_file.name.startswith("_"):
                continue
            # Build dotted module path relative to package root.
            # For "mini_agent/tools/builtin/bash_tool.py" with prefix
            # "mini_agent.tools" -> "mini_agent.tools.builtin.bash_tool".
            try:
                rel = py_file.relative_to(tools_dir).with_suffix("")
            except ValueError:
                # py_file is not under tools_dir (shouldn't happen with rglob)
                continue
            mod_name = ".".join(rel.parts)
            if module_prefix:
                mod_name = f"{module_prefix}.{mod_name}"
            self._import_tools_from_module(mod_name)

        added = len(self._tools) - count_before
        logger.info(f"discovered {added} tools from {tools_dir}")
        return added

    def _infer_module_prefix(self, tools_dir: Path) -> str | None:
        """Infer Python module path for a directory.

        e.g. /path/to/mini_agent/tools -> "mini_agent.tools"
        """
        parts = []
        cur = tools_dir.resolve()
        # Walk up until we find a directory without __init__.py
        while (cur / "__init__.py").exists():
            parts.insert(0, cur.name)
            cur = cur.parent
        return ".".join(parts) if parts else None

    def _import_tools_from_module(self, module_name: str) -> None:
        """Import a module and register all public Tool subclasses."""
        try:
            module = importlib.import_module(module_name)
        except Exception as e:
            logger.warning(f"failed to import {module_name}: {e}")
            return

        for name in dir(module):
            obj = getattr(module, name, None)
            if not isinstance(obj, type):
                continue
            if not issubclass(obj, Tool) or obj is Tool:
                continue
            if obj.__name__.startswith("_"):
                continue
            # Skip if the class is defined elsewhere (imported, not defined here)
            if obj.__module__ != module_name:
                continue
            try:
                instance = obj()
                self.register_tool(instance)
            except TypeError as e:
                # Constructor needs args - skip (user should register manually)
                logger.debug(f"skip {obj.__name__} (no default constructor): {e}")
            except Exception as e:
                logger.warning(f"failed to instantiate {obj.__name__}: {e}")

    # -------- MCP (external servers) --------

    async def load_mcp_servers(self, config_path: str = "mcp.json") -> None:
        """Connect to MCP servers defined in config (multi-path fallback)."""
        if self._mcp_loaded:
            return
        try:
            from ..tools.mcp_loader import load_mcp_tools_async

            tools = await load_mcp_tools_async(config_path)
            self._mcp_tools.extend(tools)
            logger.info(f"loaded {len(tools)} MCP tools")
        except Exception as e:
            logger.warning(f"failed to load MCP servers: {e}")
        finally:
            self._mcp_loaded = True

    async def cleanup_mcp(self) -> None:
        """Disconnect all MCP servers."""
        try:
            from ..tools.mcp_loader import cleanup_mcp_connections

            await cleanup_mcp_connections()
        except Exception:
            pass
        self._mcp_tools.clear()
        self._mcp_loaded = False

    # -------- Skills (Anthropic-style folders) --------

    def discover_skills(self) -> int:
        """Auto-discover skills from skills_dirs (multi-path search)."""
        self._skill_manager.discover()
        n = len(self._skill_manager.list_skills())
        logger.info(f"discovered {n} skills")
        return n

    def get_skill(self, name: str) -> Skill | None:
        return self._skill_manager.get(name)

    def skill_names(self) -> list[str]:
        return self._skill_manager.list_skills()

    # -------- Aggregation (unified interface) --------

    def all_tools(self) -> list[Tool]:
        """All tools the LLM can call: tools + MCP + (run_skill if skills exist)."""
        tools = list(self._tools)
        tools.extend(self._mcp_tools)
        if self._skill_manager.list_skills():
            tools.append(_SkillRunnerTool(self))
        return tools

    def system_prompt_addition(self) -> str:
        """Additional system prompt content from skills."""
        return self._skill_manager.summary_prompt()

    def stats(self) -> dict[str, int]:
        """Summary counts for logging."""
        return {
            "tools": len(self._tools),
            "mcp_tools": len(self._mcp_tools),
            "skills": len(self._skill_manager.list_skills()),
            "total": len(self.all_tools()),
        }


__all__ = ["Plugins", "Skill", "SkillManager"]