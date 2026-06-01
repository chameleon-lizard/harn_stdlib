"""Tests for initial message building, ported from initial-message.test.ts.

Tests the buildInitialMessage helper that merges piped stdin, file text,
and CLI messages into the initial prompt.
"""

from __future__ import annotations

from harn_coding_agent.cli.args import Args
from harn_coding_agent.cli.initial_message import build_initial_message


def _create_args(messages: list[str] | None = None) -> Args:
    return Args(messages=list(messages or []))


class TestBuildInitialMessage:
    """Ported from initial-message.test.ts."""

    def test_merges_piped_stdin_with_first_cli_message_into_one_prompt(self) -> None:
        parsed = _create_args(["Summarize the text given"])
        result = build_initial_message(
            parsed=parsed,
            stdinContent="README contents\n",
        )

        assert result.initialMessage == "README contents\nSummarize the text given"
        assert parsed.messages == []

    def test_uses_stdin_as_initial_prompt_when_no_cli_message_present(self) -> None:
        parsed = _create_args()
        result = build_initial_message(
            parsed=parsed,
            stdinContent="README contents",
        )

        assert result.initialMessage == "README contents"
        assert parsed.messages == []

    def test_combines_stdin_file_text_and_first_cli_message(self) -> None:
        parsed = _create_args(["Explain it", "Second message"])
        result = build_initial_message(
            parsed=parsed,
            stdinContent="stdin\n",
            fileText="file\n",
        )

        assert result.initialMessage == "stdin\nfile\nExplain it"
        assert parsed.messages == ["Second message"]
