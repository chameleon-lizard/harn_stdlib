"""OpenRouter chat-completions client implemented with urllib."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .config import DEFAULT_BASE_URL, DEFAULT_TIMEOUT_SECONDS


class OpenRouterError(RuntimeError):
    """Raised when OpenRouter rejects or fails a request."""


@dataclass
class OpenRouterClient:
    """Small OpenAI-compatible client for OpenRouter chat completions."""

    api_key: str
    model: str
    base_url: str = DEFAULT_BASE_URL
    timeout: int = DEFAULT_TIMEOUT_SECONDS
    referer: str = "https://github.com/secemp9/harn"
    title: str = "harn-stdlib"

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        reasoning: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send one chat-completions request and return the decoded JSON."""

        if not self.api_key:
            raise OpenRouterError("OPENROUTER_API_KEY is required")

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if reasoning:
            payload["reasoning"] = reasoning
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        body = json.dumps(payload).encode("utf-8")
        url = self.base_url.rstrip("/") + "/chat/completions"
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "HTTP-Referer": self.referer,
                "X-Title": self.title,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                response_body = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise OpenRouterError(f"OpenRouter HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise OpenRouterError(f"OpenRouter request failed: {exc.reason}") from exc

        try:
            data = json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise OpenRouterError(f"OpenRouter returned invalid JSON: {response_body[:500]}") from exc

        if "error" in data:
            raise OpenRouterError(f"OpenRouter error: {data['error']}")
        if not data.get("choices"):
            raise OpenRouterError(f"OpenRouter response has no choices: {data}")
        return data

    def list_models(self) -> list[dict[str, Any]]:
        """Return OpenRouter model metadata."""

        url = self.base_url.rstrip("/") + "/models"
        headers = {
            "Accept": "application/json",
            "HTTP-Referer": self.referer,
            "X-Title": self.title,
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                response_body = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise OpenRouterError(f"OpenRouter HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise OpenRouterError(f"OpenRouter request failed: {exc.reason}") from exc

        try:
            data = json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise OpenRouterError(f"OpenRouter returned invalid JSON: {response_body[:500]}") from exc
        models = data.get("data")
        if not isinstance(models, list):
            raise OpenRouterError(f"OpenRouter model response has no data list: {data}")
        return [model for model in models if isinstance(model, dict)]
