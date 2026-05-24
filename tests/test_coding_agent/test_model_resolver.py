from __future__ import annotations

from dataclasses import dataclass

import pytest
from harnify_ai.types import Model
from harnify_coding_agent.core.model_resolver import (
    defaultModelPerProvider,
    findInitialModel,
    parseModelPattern,
    resolveCliModel,
    resolveModelScope,
    restoreModelFromSession,
)


def _model(provider: str, model_id: str, *, name: str | None = None) -> Model:
    return Model(
        id=model_id,
        name=name or model_id,
        api="anthropic-messages",
        provider=provider,
        baseUrl=f"https://{provider}.example.com",
        reasoning=True,
        input=["text"],
        cost={"input": 1, "output": 2, "cacheRead": 0.1, "cacheWrite": 0.2},
        contextWindow=128000,
        maxTokens=8192,
    )


ALL_MODELS = [
    _model("anthropic", "claude-sonnet-4-5", name="Claude Sonnet 4.5"),
    _model("openai", "gpt-4o", name="GPT-4o"),
    _model("openrouter", "qwen/qwen3-coder:exacto", name="Qwen Exacto"),
    _model("openrouter", "openai/gpt-4o:extended", name="GPT-4o Extended"),
]


def test_parse_model_pattern_handles_models_with_colons_and_thinking_levels() -> None:
    result = parseModelPattern("openrouter/qwen/qwen3-coder:exacto:high", ALL_MODELS)

    assert result.model is not None
    assert result.model.provider == "openrouter"
    assert result.model.id == "qwen/qwen3-coder:exacto"
    assert result.thinkingLevel == "high"
    assert result.warning is None


def test_parse_model_pattern_warns_on_invalid_thinking_suffix() -> None:
    result = parseModelPattern("sonnet:random", ALL_MODELS)

    assert result.model is not None
    assert result.model.id == "claude-sonnet-4-5"
    assert result.thinkingLevel is None
    assert result.warning is not None
    assert "Invalid thinking level" in result.warning


def test_resolve_cli_model_prefers_exact_gateway_style_ids() -> None:
    registry = type("Registry", (), {"getAll": lambda self: ALL_MODELS})()

    result = resolveCliModel({"cliModel": "openai/gpt-4o:extended", "modelRegistry": registry})

    assert result.error is None
    assert result.model is not None
    assert result.model.provider == "openrouter"
    assert result.model.id == "openai/gpt-4o:extended"


def test_resolve_cli_model_allows_custom_ids_for_explicit_provider() -> None:
    registry = type("Registry", (), {"getAll": lambda self: ALL_MODELS})()

    result = resolveCliModel(
        {
            "cliProvider": "openrouter",
            "cliModel": "openrouter/openai/ghost-model",
            "modelRegistry": registry,
        }
    )

    assert result.error is None
    assert result.model is not None
    assert result.model.provider == "openrouter"
    assert result.model.id == "openai/ghost-model"


@pytest.mark.asyncio
async def test_resolve_model_scope_matches_minimatch_segment_rules(capsys: pytest.CaptureFixture[str]) -> None:
    registry = type("Registry", (), {"getAvailable": lambda self: ALL_MODELS})()

    single_segment = await resolveModelScope(["openrouter/*"], registry)
    single_segment_captured = capsys.readouterr()

    assert single_segment == []
    assert 'Warning: No models match pattern "openrouter/*"' in single_segment_captured.err

    globstar = await resolveModelScope(["openrouter/**"], registry)
    globstar_captured = capsys.readouterr()

    assert sorted((item.model.provider, item.model.id) for item in globstar) == [
        ("openrouter", "openai/gpt-4o:extended"),
        ("openrouter", "qwen/qwen3-coder:exacto"),
    ]
    assert globstar_captured.err == ""


@pytest.mark.asyncio
async def test_find_initial_model_prefers_known_provider_defaults() -> None:
    available = [
        _model("vercel-ai-gateway", "zai/glm-5.1"),
        _model("anthropic", "claude-sonnet-4-5"),
    ]

    @dataclass
    class Registry:
        def getAvailable(self):
            return available

    result = await findInitialModel(
        {
            "scopedModels": [],
            "isContinuing": False,
            "modelRegistry": Registry(),
        }
    )

    assert result.model is not None
    assert result.model.provider == "vercel-ai-gateway"
    assert result.model.id == defaultModelPerProvider["vercel-ai-gateway"]


@pytest.mark.asyncio
async def test_find_initial_model_cli_error_exits_like_ts(capsys: pytest.CaptureFixture[str]) -> None:
    class Registry:
        def getAll(self):
            return []

    with pytest.raises(SystemExit) as exc_info:
        await findInitialModel(
            {
                "cliProvider": "unknown",
                "cliModel": "ghost",
                "scopedModels": [],
                "isContinuing": False,
                "modelRegistry": Registry(),
            }
        )

    captured = capsys.readouterr()
    assert exc_info.value.code == 1
    assert "No models available." in captured.err
    assert captured.out == ""


@pytest.mark.asyncio
async def test_restore_model_from_session_uses_stdout_for_success_and_fallback(capsys: pytest.CaptureFixture[str]) -> None:
    restored = _model("anthropic", "claude-opus-4-7")
    fallback = _model("openai", "gpt-4o")

    @dataclass
    class Registry:
        restored_model: Model | None
        available: list[Model]

        def find(self, provider: str, model_id: str) -> Model | None:
            if self.restored_model and self.restored_model.provider == provider and self.restored_model.id == model_id:
                return self.restored_model
            return None

        def hasConfiguredAuth(self, model: Model) -> bool:
            return self.restored_model is not None and model.id == self.restored_model.id

        def getAvailable(self) -> list[Model]:
            return self.available

    restored_result = await restoreModelFromSession(
        "anthropic",
        "claude-opus-4-7",
        None,
        True,
        Registry(restored_model=restored, available=[fallback]),
    )
    restored_captured = capsys.readouterr()

    assert restored_result["model"] is restored
    assert restored_result["fallbackMessage"] is None
    assert "Restored model: anthropic/claude-opus-4-7" in restored_captured.out
    assert restored_captured.err == ""

    fallback_result = await restoreModelFromSession(
        "anthropic",
        "missing",
        None,
        True,
        Registry(restored_model=None, available=[fallback]),
    )
    fallback_captured = capsys.readouterr()

    assert fallback_result["model"] is fallback
    assert fallback_result["fallbackMessage"] == (
        "Could not restore model anthropic/missing (model no longer exists). Using openai/gpt-4o."
    )
    assert "Falling back to: openai/gpt-4o" in fallback_captured.out
    assert "Warning: Could not restore model anthropic/missing (model no longer exists)." in fallback_captured.err


@pytest.mark.asyncio
async def test_restore_model_from_session_returns_no_fallback_message_when_no_models_available(
    capsys: pytest.CaptureFixture[str],
) -> None:
    @dataclass
    class Registry:
        def find(self, provider: str, model_id: str) -> Model | None:
            return None

        def hasConfiguredAuth(self, model: Model) -> bool:
            return False

        def getAvailable(self) -> list[Model]:
            return []

    result = await restoreModelFromSession("anthropic", "missing", None, True, Registry())
    captured = capsys.readouterr()

    assert result == {"model": None, "fallbackMessage": None}
    assert captured.out == ""
    assert "Warning: Could not restore model anthropic/missing (model no longer exists)." in captured.err


def test_model_resolver_exports_match_ts_surface() -> None:
    from harnify_coding_agent.core import model_resolver

    assert model_resolver.__all__ == [
        "InitialModelResult",
        "ParsedModelResult",
        "ResolveCliModelResult",
        "ScopedModel",
        "defaultModelPerProvider",
        "findExactModelReferenceMatch",
        "findInitialModel",
        "parseModelPattern",
        "resolveCliModel",
        "resolveModelScope",
        "restoreModelFromSession",
    ]
    assert not hasattr(model_resolver, "buildFallbackModel")
    assert not hasattr(model_resolver, "tryMatchModel")
    assert not hasattr(model_resolver, "isAlias")
    assert not hasattr(model_resolver, "isValidThinkingLevel")
