"""Tests for frontmatter parsing, ported from frontmatter.test.ts.

Tests the YAML frontmatter parser that extracts metadata from skill and
prompt template files.
"""

from __future__ import annotations

import pytest

from harn_coding_agent.utils.frontmatter import parse_frontmatter, strip_frontmatter


class TestParseFrontmatter:
    """Ported from frontmatter.test.ts."""

    def test_parses_keys_strips_quotes_and_returns_body(self) -> None:
        text = '---\nname: "skill-name"\ndescription: \'A desc\'\nfoo-bar: value\n---\n\nBody text'
        result = parse_frontmatter(text)

        assert result.frontmatter["name"] == "skill-name"
        assert result.frontmatter["description"] == "A desc"
        assert result.frontmatter["foo-bar"] == "value"
        assert result.body == "Body text"

    def test_normalizes_newlines_and_handles_crlf(self) -> None:
        text = "---\r\nname: test\r\n---\r\nLine one\r\nLine two"
        result = parse_frontmatter(text)
        assert result.body == "Line one\nLine two"

    def test_parses_pipe_multiline_yaml_syntax(self) -> None:
        text = "---\ndescription: |\n  Line one\n  Line two\n---\n\nBody"
        result = parse_frontmatter(text)
        assert result.frontmatter["description"] == "Line one\nLine two\n"
        assert result.body == "Body"

    def test_returns_original_content_when_frontmatter_missing(self) -> None:
        no_frontmatter = "Just text\nsecond line"
        result = parse_frontmatter(no_frontmatter)
        assert result.body == "Just text\nsecond line"

    def test_returns_original_content_when_frontmatter_unterminated(self) -> None:
        missing_end = "---\nname: test\nBody without terminator"
        result = parse_frontmatter(missing_end)
        assert result.body == "---\nname: test\nBody without terminator"

    def test_returns_empty_object_for_comment_only_frontmatter(self) -> None:
        text = "---\n# just a comment\n---\nBody"
        result = parse_frontmatter(text)
        assert result.frontmatter == {}


class TestStripFrontmatter:
    """Ported from frontmatter.test.ts."""

    def test_removes_frontmatter_and_trims_body(self) -> None:
        text = "---\nkey: value\n---\n\nBody\n"
        assert strip_frontmatter(text) == "Body"

    def test_returns_body_when_no_frontmatter_present(self) -> None:
        text = "\n  No frontmatter body  \n"
        assert strip_frontmatter(text) == "\n  No frontmatter body  \n"
