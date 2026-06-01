"""Tests for getSupportedThinkingLevels xhigh support, ported from supports-xhigh.test.ts.

Tests that the model registry correctly reports xhigh thinking level support
for applicable models (Opus 4.6+, gpt-5.4+, DeepSeek V4 Flash, etc.).
"""

from __future__ import annotations

import pytest

from harn_ai.models import get_model, get_supported_thinking_levels


class TestGetSupportedThinkingLevels:
    """Ported from supports-xhigh.test.ts."""

    def test_includes_xhigh_for_anthropic_opus_4_6(self) -> None:
        model = get_model("anthropic", "claude-opus-4-6")
        if model is None:
            pytest.skip("claude-opus-4-6 not in model registry")
        assert "xhigh" in get_supported_thinking_levels(model)

    def test_includes_xhigh_for_anthropic_opus_4_7(self) -> None:
        model = get_model("anthropic", "claude-opus-4-7")
        if model is None:
            pytest.skip("claude-opus-4-7 not in model registry")
        assert "xhigh" in get_supported_thinking_levels(model)

    def test_does_not_include_xhigh_for_non_opus_anthropic_models(self) -> None:
        model = get_model("anthropic", "claude-sonnet-4-5")
        if model is None:
            pytest.skip("claude-sonnet-4-5 not in model registry")
        assert "xhigh" not in get_supported_thinking_levels(model)

    @pytest.mark.parametrize("model_id", ["gpt-5.4", "gpt-5.5"])
    def test_includes_xhigh_for_codex_models(self, model_id: str) -> None:
        model = get_model("openai-codex", model_id)
        if model is None:
            pytest.skip(f"{model_id} not in model registry for openai-codex")
        assert "xhigh" in get_supported_thinking_levels(model)

    def test_deepseek_v4_flash_on_deepseek_provider(self) -> None:
        model = get_model("deepseek", "deepseek-v4-flash")
        if model is None:
            pytest.skip("deepseek-v4-flash not in model registry")
        levels = get_supported_thinking_levels(model)
        assert levels == ["off", "high", "xhigh"]

    def test_deepseek_v4_flash_on_opencode_go(self) -> None:
        model = get_model("opencode-go", "deepseek-v4-flash")
        if model is None:
            pytest.skip("deepseek-v4-flash not on opencode-go")
        levels = get_supported_thinking_levels(model)
        assert levels == ["off", "high", "xhigh"]

    def test_deepseek_v4_flash_on_openrouter(self) -> None:
        model = get_model("openrouter", "deepseek/deepseek-v4-flash")
        if model is None:
            pytest.skip("deepseek/deepseek-v4-flash not on openrouter")
        levels = get_supported_thinking_levels(model)
        assert levels == ["off", "high", "xhigh"]

    def test_includes_xhigh_for_openrouter_opus_4_6(self) -> None:
        model = get_model("openrouter", "anthropic/claude-opus-4.6")
        if model is None:
            pytest.skip("anthropic/claude-opus-4.6 not on openrouter")
        assert "xhigh" in get_supported_thinking_levels(model)
