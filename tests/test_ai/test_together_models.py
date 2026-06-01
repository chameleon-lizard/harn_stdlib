"""Tests for Together AI model registration, ported from together-models.test.ts.

Tests that Together AI models are registered with correct API, provider,
base URL, and compat settings.
"""

from __future__ import annotations

import os

import pytest

from harn_ai.env_api_keys import find_env_keys, get_env_api_key
from harn_ai.models import get_model


class TestTogetherModels:
    """Ported from together-models.test.ts."""

    def test_registers_kimi_k2_6_via_openai_compatible_api(self) -> None:
        model = get_model("together", "moonshotai/Kimi-K2.6")
        if model is None:
            pytest.skip("moonshotai/Kimi-K2.6 not in model registry")

        assert model.api == "openai-completions"
        assert model.provider == "together"
        assert model.baseUrl == "https://api.together.ai/v1"
        assert model.reasoning is True
        assert model.thinkingLevelMap == {"minimal": None, "low": None, "medium": None}
        assert model.input == ["text", "image"]
        assert model.contextWindow == 262144
        assert model.maxTokens == 131000
        assert model.cost.input == 1.2
        assert model.cost.output == 4.5
        assert model.cost.cacheRead == 0.2
        assert model.cost.cacheWrite == 0

        assert model.compat is not None
        assert model.compat.supportsStore is False
        assert model.compat.supportsDeveloperRole is False
        assert model.compat.supportsReasoningEffort is False
        assert model.compat.maxTokensField == "max_tokens"
        assert model.compat.thinkingFormat == "together"
        assert model.compat.supportsStrictMode is False
        assert model.compat.supportsLongCacheRetention is False

    def test_together_reasoning_controls(self) -> None:
        gpt_oss = get_model("together", "openai/gpt-oss-120b")
        if gpt_oss is None:
            pytest.skip("openai/gpt-oss-120b not in model registry")
        assert gpt_oss.thinkingLevelMap == {"off": None, "minimal": None}
        assert gpt_oss.compat is not None
        assert gpt_oss.compat.supportsReasoningEffort is True
        assert gpt_oss.compat.thinkingFormat == "openai"

        deep_seek_v4 = get_model("together", "deepseek-ai/DeepSeek-V4-Pro")
        if deep_seek_v4 is None:
            pytest.skip("deepseek-ai/DeepSeek-V4-Pro not in model registry")
        assert deep_seek_v4.thinkingLevelMap == {
            "minimal": None,
            "low": None,
            "medium": None,
            "high": "high",
            "xhigh": None,
        }
        assert deep_seek_v4.compat is not None
        assert deep_seek_v4.compat.supportsReasoningEffort is True
        assert deep_seek_v4.compat.thinkingFormat == "together"

        minimax = get_model("together", "MiniMaxAI/MiniMax-M2.7")
        if minimax is None:
            pytest.skip("MiniMaxAI/MiniMax-M2.7 not in model registry")
        assert minimax.thinkingLevelMap == {"off": None, "minimal": None, "low": None, "medium": None}
        assert minimax.compat is not None
        assert minimax.compat.thinkingFormat is None
        assert minimax.compat.supportsReasoningEffort is False

    def test_resolves_together_api_key_from_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TOGETHER_API_KEY", "test-together-key")

        assert find_env_keys("together") == ["TOGETHER_API_KEY"]
        assert get_env_api_key("together") == "test-together-key"
