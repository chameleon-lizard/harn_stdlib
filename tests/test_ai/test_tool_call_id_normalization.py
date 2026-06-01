"""Tests for tool call ID normalization, ported from tool-call-id-normalization.test.ts.

The TS test is E2E (sends requests through live providers). The Python port
unit-tests the normalization functions that each provider uses to sanitize
tool call IDs, particularly the pipe-separated format from OpenAI Responses API.
"""

from __future__ import annotations

import re

from harn_ai.providers.openai_responses_shared import _normalize_id_part, _build_foreign_responses_item_id
from harn_ai.providers.anthropic import normalize_tool_call_id as anthropic_normalize
from harn_ai.providers.amazon_bedrock import normalize_tool_call_id as bedrock_normalize
from harn_ai.providers.mistral import derive_mistral_tool_call_id


# The exact failing ID from issue #1022
FAILING_TOOL_CALL_ID = (
    "call_pAYbIr76hXIjncD9UE4eGfnS|t5nnb2qYMFWGSsr13fhCd1CaCu3t3qONEPuOudu4HSVEtA8YJSL6FAZUx"
    "voOoD792VIJWl91g87EdqsCWp9krVsdBysQoDaf9lMCLb8BS4EYi4gQd5kBQBYLlgD71PYwvf+TbMD9J9/5OMD42o"
    "xSRj8H+vRf78/l2Xla33LWz4nOgsddBlbvabICRs8GHt5C9PK5keFtzyi3lsyVKNlfduK3iphsZqs4MLv4zyGJn"
    "vZo/+QzShyk5xnMSQX/f98+aEoNflEApCdEOXipipgeiNWnpFSHbcwmMkZoJhURNu+JEz3xCh1mrXeYoN5o+trL"
    "L3IXJacSsLYXDrYTipZZbJFRPAucgbnjYBC+/ZzJOfkwCs+Gkw7EoZR7ZQgJ8ma+9586n4tT4cI8DEhBSZsWMjr"
    "Ct8dxKg=="
)


class TestNormalizeIdPart:
    """Tests for _normalize_id_part from openai_responses_shared."""

    def test_passes_through_simple_alphanumeric_ids(self) -> None:
        assert _normalize_id_part("call_abc123") == "call_abc123"

    def test_replaces_special_characters_with_underscore(self) -> None:
        result = _normalize_id_part("call_abc+def/ghi=jkl")
        assert "+" not in result
        assert "/" not in result
        assert "=" not in result
        assert re.fullmatch(r"[a-zA-Z0-9_-]+", result)

    def test_truncates_to_64_characters(self) -> None:
        long_id = "a" * 100
        result = _normalize_id_part(long_id)
        assert len(result) <= 64

    def test_strips_trailing_underscores(self) -> None:
        result = _normalize_id_part("abc===")
        assert not result.endswith("_")

    def test_handles_empty_string(self) -> None:
        result = _normalize_id_part("")
        assert result == ""

    def test_handles_only_special_chars(self) -> None:
        result = _normalize_id_part("+++///===")
        # All chars replaced with underscores, trailing underscores stripped
        assert not result.endswith("_") or result == ""


class TestBuildForeignResponsesItemId:
    """Tests for _build_foreign_responses_item_id."""

    def test_produces_fc_prefixed_hash(self) -> None:
        result = _build_foreign_responses_item_id("some_long_item_id")
        assert result.startswith("fc_")

    def test_output_within_64_chars(self) -> None:
        result = _build_foreign_responses_item_id("x" * 500)
        assert len(result) <= 64


class TestAnthropicNormalize:
    """Tests for Anthropic provider's normalize_tool_call_id."""

    def test_keeps_alphanumeric_and_dash_underscore(self) -> None:
        assert anthropic_normalize("call_abc-123_def") == "call_abc-123_def"

    def test_replaces_pipe_with_underscore(self) -> None:
        result = anthropic_normalize("call_abc|item_def")
        assert "|" not in result
        assert "_" in result

    def test_truncates_to_64_chars(self) -> None:
        result = anthropic_normalize("a" * 100)
        assert len(result) <= 64

    def test_handles_failing_issue_1022_id(self) -> None:
        result = anthropic_normalize(FAILING_TOOL_CALL_ID)
        assert len(result) <= 64
        assert "|" not in result
        assert "+" not in result
        assert "/" not in result
        assert "=" not in result


class TestBedrockNormalize:
    """Tests for Bedrock provider's normalize_tool_call_id."""

    def test_replaces_special_characters(self) -> None:
        result = bedrock_normalize("call_abc+def/ghi=jkl")
        assert re.fullmatch(r"[a-zA-Z0-9_-]+", result)

    def test_truncates_to_64_chars(self) -> None:
        result = bedrock_normalize("x" * 200)
        assert len(result) <= 64

    def test_handles_failing_issue_1022_id(self) -> None:
        result = bedrock_normalize(FAILING_TOOL_CALL_ID)
        assert len(result) <= 64


class TestMistralDerive:
    """Tests for Mistral's derive_mistral_tool_call_id."""

    def test_alphanumeric_9_char_input_passes_through_on_attempt_0(self) -> None:
        result = derive_mistral_tool_call_id("abc123def", 0)
        assert result == "abc123def"

    def test_long_input_is_hashed_to_9_chars(self) -> None:
        result = derive_mistral_tool_call_id("very_long_tool_call_id_with_special_chars", 0)
        assert len(result) == 9
        assert result.isalnum()

    def test_different_attempts_produce_different_ids(self) -> None:
        id0 = derive_mistral_tool_call_id("same_input", 0)
        id1 = derive_mistral_tool_call_id("same_input", 1)
        assert id0 != id1

    def test_handles_failing_issue_1022_id(self) -> None:
        result = derive_mistral_tool_call_id(FAILING_TOOL_CALL_ID, 0)
        assert len(result) == 9
        assert result.isalnum()
