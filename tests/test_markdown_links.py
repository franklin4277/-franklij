"""Test for Markdown link path processing in SkillManager (core/skill.py).

SkillManager.load_skill() applies Progressive Disclosure Level 3+: rewrites
relative paths in SKILL.md body to absolute paths so the agent can read
nested resources from any cwd.
"""

import tempfile
from pathlib import Path

from mini_agent.core.skill import SkillManager


def test_markdown_link_processing():
    """SkillManager.load_skill() rewrites Markdown links to absolute paths."""

    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir)
        skill_dir = skills_dir / "test-skill"
        skill_dir.mkdir(parents=True)

        (skill_dir / "reference").mkdir()
        (skill_dir / "scripts").mkdir()

        doc_file = skill_dir / "reference.md"
        doc_file.write_text("# Reference Documentation")
        ref_file = skill_dir / "reference" / "guide.md"
        ref_file.write_text("# Guide")
        script_file = skill_dir / "scripts" / "helper.js"
        script_file.write_text("// Helper script")

        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("""---
name: test-skill
description: Test skill for Markdown link processing
---

# Test Skill

## Instructions

1. Read [`reference.md`](reference.md) for basic documentation.
2. Load [Guide](./reference/guide.md) for detailed instructions.
3. Use [helper script](scripts/helper.js) for automation.
4. See [another reference](./reference.md) without prefix word.
""")

        mgr = SkillManager([skills_dir])
        mgr.discover()
        skills = mgr.all()
        assert len(skills) == 1
        skill = skills[0]
        body = skill.instructions

        # Simple filename link rewritten to absolute
        assert str(doc_file) in body, f"simple filename link not rewritten: {body!r}"
        assert "](reference.md)" not in body, "relative path 'reference.md' not replaced"

        # ./reference/ prefix link rewritten
        assert str(ref_file) in body, f"./reference/ link not rewritten: {body!r}"
        assert "](./reference/guide.md)" not in body, "./reference/ path not replaced"

        # scripts/ directory link rewritten
        assert str(script_file) in body, f"scripts/ link not rewritten: {body!r}"
        assert "](scripts/helper.js)" not in body, "scripts/ path not replaced"

        # All three should have the "use read_file" hint appended
        assert body.count("(use read_file to access)") >= 3, "hint missing on some links"


def test_run_skill_tool_via_plugins():
    """Plugins registers run_skill tool when skills are discovered."""

    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir)
        skill_dir = skills_dir / "my-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: test\nwhen_to_use: testing\n---\n# Body\n"
        )

        from mini_agent.core.plugins import Plugins
        plugins = Plugins(skills_dirs=[skills_dir])
        plugins.discover_skills()
        tools = plugins.all_tools()
        assert "run_skill" in [t.name for t in tools], "run_skill tool not registered"

        # Invoke run_skill
        run_skill = next(t for t in tools if t.name == "run_skill")
        import asyncio
        result = asyncio.run(run_skill.execute(skill_name="my-skill", input="hello"))
        assert result.success
        assert "my-skill" in result.content
        assert "# Body" in result.content
        assert "hello" in result.content  # user input echoed

        # System prompt addition references run_skill usage
        sp = plugins.system_prompt_addition()
        assert "my-skill" in sp
        assert "run_skill" in sp


if __name__ == "__main__":
    test_markdown_link_processing()
    test_run_skill_tool_via_plugins()
    print("✅ all markdown link + run_skill tests passed")
