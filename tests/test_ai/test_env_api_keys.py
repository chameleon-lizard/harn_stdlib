"""Tests for environment API key resolution, ported from env-api-keys.test.ts.

Tests that the env key resolver correctly distinguishes between generic GitHub
tokens and the specific COPILOT_GITHUB_TOKEN used for GitHub Copilot auth.
"""

from __future__ import annotations

import pytest

from harn_ai.env_api_keys import find_env_keys, get_env_api_key


class TestEnvironmentApiKeys:
    """Ported from env-api-keys.test.ts."""

    def test_does_not_treat_generic_github_tokens_as_copilot_credentials(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("COPILOT_GITHUB_TOKEN", raising=False)
        monkeypatch.setenv("GH_TOKEN", "gh-token")
        monkeypatch.setenv("GITHUB_TOKEN", "github-token")

        assert find_env_keys("github-copilot") is None
        assert get_env_api_key("github-copilot") is None

    def test_resolves_copilot_credentials_from_copilot_github_token(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("COPILOT_GITHUB_TOKEN", "copilot-token")
        monkeypatch.setenv("GH_TOKEN", "gh-token")
        monkeypatch.setenv("GITHUB_TOKEN", "github-token")

        assert find_env_keys("github-copilot") == ["COPILOT_GITHUB_TOKEN"]
        assert get_env_api_key("github-copilot") == "copilot-token"

    def test_resolves_anthropic_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.delenv("ANTHROPIC_OAUTH_TOKEN", raising=False)

        assert find_env_keys("anthropic") == ["ANTHROPIC_API_KEY"]
        assert get_env_api_key("anthropic") == "sk-ant-test"

    def test_prefers_anthropic_oauth_token_over_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_OAUTH_TOKEN", "oauth-token")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "api-key")

        keys = find_env_keys("anthropic")
        assert keys is not None
        assert "ANTHROPIC_OAUTH_TOKEN" in keys
        assert get_env_api_key("anthropic") == "oauth-token"

    def test_resolves_openai_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

        assert find_env_keys("openai") == ["OPENAI_API_KEY"]
        assert get_env_api_key("openai") == "sk-test"

    def test_returns_none_for_unknown_provider(self) -> None:
        assert find_env_keys("nonexistent-provider") is None
        assert get_env_api_key("nonexistent-provider") is None
