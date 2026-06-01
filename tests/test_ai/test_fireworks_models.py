"""Tests for Fireworks model registration, ported from fireworks-models.test.ts.

Tests that Fireworks models are registered correctly with the Anthropic-compatible
Messages API, proper compat settings, and env key resolution.
"""

from __future__ import annotations

import pytest

from harn_ai.env_api_keys import find_env_keys, get_env_api_key
from harn_ai.models import get_model


class TestFireworksModels:
    """Ported from fireworks-models.test.ts (model registration section only)."""

    def test_registers_kimi_k2p6_via_anthropic_messages_api(self) -> None:
        model = get_model("fireworks", "accounts/fireworks/models/kimi-k2p6")
        if model is None:
            pytest.skip("kimi-k2p6 not in model registry")

        assert model.api == "anthropic-messages"
        assert model.provider == "fireworks"
        assert model.baseUrl == "https://api.fireworks.ai/inference"
        assert model.reasoning is True
        assert model.input == ["text", "image"]
        assert model.contextWindow == 262000
        assert model.maxTokens == 262000
        assert model.cost.input == 0.95
        assert model.cost.output == 4
        assert model.cost.cacheRead == 0.16
        assert model.cost.cacheWrite == 0

    def test_registers_fire_pass_turbo_router_model(self) -> None:
        model = get_model("fireworks", "accounts/fireworks/routers/kimi-k2p5-turbo")
        if model is None:
            pytest.skip("kimi-k2p5-turbo not in model registry")

        assert model.api == "anthropic-messages"
        assert model.baseUrl == "https://api.fireworks.ai/inference"
        assert model.input == ["text", "image"]

    def test_resolves_fireworks_api_key_from_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FIREWORKS_API_KEY", "test-fireworks-key")

        assert find_env_keys("fireworks") == ["FIREWORKS_API_KEY"]
        assert get_env_api_key("fireworks") == "test-fireworks-key"

    def test_fireworks_compat_for_session_affinity_and_tool_fields(self) -> None:
        model = get_model("fireworks", "accounts/fireworks/models/kimi-k2p6")
        if model is None:
            pytest.skip("kimi-k2p6 not in model registry")

        assert model.compat is not None
        assert model.compat.sendSessionAffinityHeaders is True
        assert model.compat.supportsEagerToolInputStreaming is False
        assert model.compat.supportsCacheControlOnTools is False
        assert model.compat.supportsLongCacheRetention is False
