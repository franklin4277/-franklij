"""Skill - Anthropic-style: a folder with SKILL.md + optional scripts/references/assets.

Structure:
    skills/
    └── <skill_name>/
        ├── SKILL.md           # required: YAML frontmatter + Markdown
        ├── scripts/           # optional: Python scripts the model can call
        ├── references/        # optional: docs to load on demand
        └── assets/            # optional: templates, fonts, etc.

SKILL.md format:
    ---
    name: my_skill
    description: One-line description
    when_to_use: When to invoke this skill
    inputs:
      - question: string (required)
      - datasource_id: integer (optional)
    ---

    # my_skill

    Full workflow instructions in Markdown...
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class Skill:
    """One Anthropic-style Skill. A folder, not a class."""

    folder: Path
    frontmatter: dict = field(default_factory=dict)
    instructions: str = ""  # SKILL.md body without YAML

    @property
    def name(self) -> str:
        return self.frontmatter.get("name", self.folder.name)

    @property
    def description(self) -> str:
        return self.frontmatter.get("description", "")

    @property
    def when_to_use(self) -> str:
        return self.frontmatter.get("when_to_use", "")

    def read_reference(self, name: str) -> str:
        """Load a reference file on demand."""
        path = self.folder / "references" / name
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def list_scripts(self) -> list[Path]:
        """Return Python scripts available in this skill."""
        scripts_dir = self.folder / "scripts"
        if not scripts_dir.exists():
            return []
        return sorted(scripts_dir.glob("*.py"))

    def summary(self) -> str:
        """One-line summary for system prompt."""
        return f"- {self.name}: {self.description}"


def _process_skill_paths(content: str, skill_dir: Path) -> str:
    """Rewrite relative paths in SKILL.md body to absolute paths.

    Implements Progressive Disclosure Level 3+: converts relative file
    references (scripts/, references/, assets/, markdown links, doc refs)
    to absolute paths so the agent can read nested resources from any cwd.
    Ported from the legacy SkillLoader so the modern path is feature-equivalent.
    """
    # Pattern 1: Directory-based paths (scripts/, references/, assets/)
    def replace_dir_path(match):
        prefix = match.group(1)
        rel_path = match.group(2)
        abs_path = skill_dir / rel_path
        if abs_path.exists():
            return f"{prefix}{abs_path}"
        return match.group(0)

    pattern_dirs = r"(python\s+|`)((?:scripts|references|assets)/[^\s`\)]+)"
    content = re.sub(pattern_dirs, replace_dir_path, content)

    # Pattern 2: Direct markdown/document references ("see reference.md")
    def replace_doc_path(match):
        prefix = match.group(1)
        filename = match.group(2)
        suffix = match.group(3)
        abs_path = skill_dir / filename
        if abs_path.exists():
            return f"{prefix}`{abs_path}` (use read_file to access){suffix}"
        return match.group(0)

    pattern_docs = r"(see|read|refer to|check)\s+([a-zA-Z0-9_-]+\.(?:md|txt|json|yaml))([.,;\s])"
    content = re.sub(pattern_docs, replace_doc_path, content, flags=re.IGNORECASE)

    # Pattern 3: Markdown links - [`file.md`](file.md), [text](./ref/file.md), [text](scripts/file.js)
    def replace_markdown_link(match):
        prefix = match.group(1) if match.group(1) else ""
        link_text = match.group(2)
        filepath = match.group(3)
        clean_path = filepath[2:] if filepath.startswith("./") else filepath
        abs_path = skill_dir / clean_path
        if abs_path.exists():
            return f"{prefix}[{link_text}](`{abs_path}`) (use read_file to access)"
        return match.group(0)

    pattern_markdown = (
        r"(?:(Read|See|Check|Refer to|Load|View)\s+)?\[(`?[^`\]]+`?)\]\(((?:\./)?[^)]+\.(?:md|txt|json|yaml|js|py|html))\)"
    )
    content = re.sub(pattern_markdown, replace_markdown_link, content, flags=re.IGNORECASE)

    return content


def load_skill(folder: Path) -> Skill | None:
    """Load a Skill from a folder containing SKILL.md.

    Returns None if folder is not a valid skill.
    """
    skill_md = folder / "SKILL.md"
    if not skill_md.exists():
        return None

    content = skill_md.read_text(encoding="utf-8")
    if not content.startswith("---"):
        logger.warning(f"SKILL.md in {folder} missing YAML frontmatter")
        return None

    parts = content.split("---", 2)
    if len(parts) < 3:
        return None

    try:
        frontmatter = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as e:
        logger.error(f"Invalid YAML in {folder}/SKILL.md: {e}")
        return None

    if not frontmatter.get("name") or not frontmatter.get("description"):
        logger.warning(
            f"SKILL.md in {folder} missing required frontmatter fields "
            f"(name and description); skipping skill"
        )
        return None

    body = parts[2].strip()
    # Rewrite relative paths to absolute (Progressive Disclosure Level 3+)
    body = _process_skill_paths(body, folder)
    return Skill(folder=folder, frontmatter=frontmatter, instructions=body)


class SkillManager:
    """Discovers and manages Anthropic-style skills from filesystem (multi-path).

    Skills are searched in priority order. First-found wins (later paths don't
    override earlier ones). This lets users override built-in skills.

    Usage:
        mgr = SkillManager(["./skills", "mini_agent/skills"])
        mgr.discover()
        print(mgr.list_skills())  # ["data_query", "web_search", ...]
    """

    def __init__(self, skills_dirs: str | Path | list[str | Path] = "./skills"):
        if isinstance(skills_dirs, (str, Path)):
            skills_dirs = [skills_dirs]
        self.skills_dirs = [Path(d).expanduser() for d in skills_dirs]
        self._skills: dict[str, Skill] = {}

    def discover(self) -> None:
        """Scan all skills_dirs for SKILL.md files. First-found wins.

        Recursive: nested skill folders (e.g. skills/group/my-skill/SKILL.md)
        are discovered too, matching the legacy SkillLoader behavior.
        """
        # Reverse so earlier paths override later ones (last write wins)
        for skills_dir in reversed(self.skills_dirs):
            if not skills_dir.exists():
                continue
            for skill_md in sorted(skills_dir.rglob("SKILL.md")):
                folder = skill_md.parent
                if folder.name.startswith((".", "_")):
                    continue
                skill = load_skill(folder)
                if skill:
                    self._skills[skill.name] = skill
                    logger.info(f"loaded skill: {skill.name} (from {folder.relative_to(skills_dir)})")

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def list_skills(self) -> list[str]:
        return list(self._skills.keys())

    def all(self) -> list[Skill]:
        return list(self._skills.values())

    def summary_prompt(self) -> str:
        """Build system prompt section listing all skills (for LLM awareness)."""
        if not self._skills:
            return ""
        parts = ["# Available Skills\n"]
        for skill in self._skills.values():
            parts.append(
                f"## Skill: {skill.name}\n"
                f"{skill.description}\n"
                f"**When to use**: {skill.when_to_use}\n"
                f"**Usage**: `run_skill(skill_name=\"{skill.name}\", input=\"...\")`\n"
            )
        return "\n".join(parts)

    def full_instructions(self, name: str) -> str:
        """Return full SKILL.md body for one skill (for LLM to follow)."""
        skill = self.get(name)
        return skill.instructions if skill else ""


__all__ = ["Skill", "SkillManager", "load_skill"]