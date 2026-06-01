"""Tests for HTTP proxy resolution, ported from node-http-proxy.test.ts.

Tests the environment-driven proxy resolution logic: NO_PROXY exclusions,
HTTP/HTTPS proxy URL resolution, and rejection of SOCKS/PAC protocols.
"""

from __future__ import annotations

import pytest

from harn_ai.utils.node_http_proxy import (
    UNSUPPORTED_PROXY_PROTOCOL_MESSAGE,
    resolve_http_proxy_url_for_target,
)


# All proxy-related env vars that must be cleaned between tests
_PROXY_ENV_KEYS = [
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
    "all_proxy",
    "npm_config_http_proxy",
    "npm_config_https_proxy",
    "npm_config_proxy",
    "npm_config_no_proxy",
]


@pytest.fixture(autouse=True)
def _clean_proxy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove all proxy env vars before each test."""
    for key in _PROXY_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


class TestNodeHttpProxyResolution:
    """Ported from node-http-proxy.test.ts."""

    def test_respects_no_proxy_exclusions(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:8080")
        monkeypatch.setenv("NO_PROXY", "bedrock-runtime.us-east-1.amazonaws.com")

        result = resolve_http_proxy_url_for_target(
            "https://bedrock-runtime.us-east-1.amazonaws.com"
        )
        assert result is None

    def test_resolves_http_and_https_proxy_urls(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:8080")

        result = resolve_http_proxy_url_for_target(
            "https://bedrock-runtime.us-east-1.amazonaws.com"
        )
        assert result is not None
        assert result.geturl() == "http://proxy.example:8080"

    def test_rejects_socks_proxy_urls_explicitly(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HTTPS_PROXY", "socks5://proxy.example:1080")

        with pytest.raises(RuntimeError, match=UNSUPPORTED_PROXY_PROTOCOL_MESSAGE):
            resolve_http_proxy_url_for_target(
                "https://bedrock-runtime.us-east-1.amazonaws.com"
            )

    def test_returns_none_when_no_proxy_configured(self) -> None:
        result = resolve_http_proxy_url_for_target("https://api.anthropic.com")
        assert result is None

    def test_respects_all_proxy_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ALL_PROXY", "http://all-proxy.example:3128")

        result = resolve_http_proxy_url_for_target("https://api.openai.com")
        assert result is not None
        assert "all-proxy.example" in result.geturl()

    def test_no_proxy_wildcard_blocks_all(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:8080")
        monkeypatch.setenv("NO_PROXY", "*")

        result = resolve_http_proxy_url_for_target("https://api.anthropic.com")
        assert result is None
