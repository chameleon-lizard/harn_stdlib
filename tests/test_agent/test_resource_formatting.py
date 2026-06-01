"""Tests for resource formatting helpers, ported from resource-formatting.test.ts.

Tests skill invocation formatting and prompt template invocation formatting.
"""

from __future__ import annotations

from harn_agent.harness.skills import format_skill_invocation
from harn_agent.harness.prompt_templates import format_prompt_template_invocation
from harn_agent.harness.types import PromptTemplate, Skill


class TestResourceFormattingHelpers:
    """Ported from resource-formatting.test.ts."""

    def test_formats_skill_invocations_with_additional_instructions(self) -> None:
        skill = Skill(
            name="inspect",
            description="Inspect things",
            content="Use inspection tools.",
            filePath="/project/.pi/skills/inspect/SKILL.md",
        )

        result = format_skill_invocation(skill, "Check errors.")

        expected = (
            '<skill name="inspect" location="/project/.pi/skills/inspect/SKILL.md">\n'
            "References are relative to /project/.pi/skills/inspect.\n\n"
            "Use inspection tools.\n"
            "</skill>\n\n"
            "Check errors."
        )
        assert result == expected

    def test_formats_prompt_template_invocations_with_positional_arguments(self) -> None:
        template = PromptTemplate(name="review", content="Review $1 with $ARGUMENTS")

        result = format_prompt_template_invocation(template, ["a.ts", "care"])
        assert result == "Review a.ts with a.ts care"

    def test_substitutes_command_arguments(self) -> None:
        content = "$1 ${@:2} $ARGUMENTS"
        template = PromptTemplate(name="one", content=content)

        result = format_prompt_template_invocation(template, ["hello world", "test"])
        assert result == "hello world test hello world test"
