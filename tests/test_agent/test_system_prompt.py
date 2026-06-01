"""Tests for system prompt formatting, ported from system-prompt.test.ts.

Tests the formatSkillsForSystemPrompt helper that renders model-visible
skills as XML in the system prompt.
"""

from __future__ import annotations

from harn_agent.harness.system_prompt import format_skills_for_system_prompt
from harn_agent.harness.types import Skill


_VISIBLE_SKILL = Skill(
    name="visible",
    description="Use <this> & that",
    content="visible content",
    filePath="/skills/visible/SKILL.md",
)

_SECOND_SKILL = Skill(
    name="second",
    description="Second skill",
    content="second content",
    filePath="/skills/second/SKILL.md",
)

_DISABLED_SKILL = Skill(
    name="hidden",
    description="Hidden",
    content="hidden content",
    filePath="/skills/hidden/SKILL.md",
    disableModelInvocation=True,
)


class TestFormatSkillsForSystemPrompt:
    """Ported from system-prompt.test.ts."""

    def test_formats_visible_skills_in_order_and_skips_model_disabled_skills(self) -> None:
        result = format_skills_for_system_prompt([_VISIBLE_SKILL, _DISABLED_SKILL, _SECOND_SKILL])

        expected = (
            "The following skills provide specialized instructions for specific tasks.\n"
            "Read the full skill file when the task matches its description.\n"
            "When a skill file references a relative path, resolve it against the skill directory "
            "(parent of SKILL.md / dirname of the path) and use that absolute path in tool commands.\n"
            "\n"
            "<available_skills>\n"
            "  <skill>\n"
            "    <name>visible</name>\n"
            "    <description>Use &lt;this&gt; &amp; that</description>\n"
            "    <location>/skills/visible/SKILL.md</location>\n"
            "  </skill>\n"
            "  <skill>\n"
            "    <name>second</name>\n"
            "    <description>Second skill</description>\n"
            "    <location>/skills/second/SKILL.md</location>\n"
            "  </skill>\n"
            "</available_skills>"
        )
        assert result == expected

    def test_returns_empty_string_when_no_skills_are_model_visible(self) -> None:
        assert format_skills_for_system_prompt([_DISABLED_SKILL]) == ""

    def test_escapes_xml_in_all_model_visible_skill_fields(self) -> None:
        skill = Skill(
            name="a&b",
            description='Quote "double" and \'single\'',
            content="content",
            filePath='/skills/<bad>&"quote"/SKILL.md',
        )
        result = format_skills_for_system_prompt([skill])

        assert "<name>a&amp;b</name>" in result
        assert "<description>Quote &quot;double&quot; and &apos;single&apos;</description>" in result
        assert "<location>/skills/&lt;bad&gt;&amp;&quot;quote&quot;/SKILL.md</location>" in result
