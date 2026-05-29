from __future__ import annotations

import pytest

from harn_ai.api_registry import clear_api_providers, get_api_providers
from harn_ai.models import get_model
import harn_ai.providers.register_builtins as register_builtins
from harn_ai.providers.register_builtins import LazyProviderModule, register_built_in_api_providers
from harn_ai.types import Context
from harn_ai.utils.event_stream import AssistantMessageEventStream


def _model():
    model = get_model("openai", "gpt-4o-mini")
    assert model is not None
    return model.model_copy(update={"api": "openai-responses"})


async def _failing_loader() -> LazyProviderModule:
    raise RuntimeError("load boom")


async def _unused_simple_stream(*_args, **_kwargs):
    if False:
        yield None


def test_register_builtins_exports_expected_names() -> None:
    assert register_builtins.__all__ == [
        "setBedrockProviderModule",
        "streamAnthropic",
        "streamSimpleAnthropic",
        "streamAzureOpenAIResponses",
        "streamSimpleAzureOpenAIResponses",
        "streamGoogle",
        "streamSimpleGoogle",
        "streamGoogleVertex",
        "streamSimpleGoogleVertex",
        "streamMistral",
        "streamSimpleMistral",
        "streamOpenAICodexResponses",
        "streamSimpleOpenAICodexResponses",
        "streamOpenAICompletions",
        "streamSimpleOpenAICompletions",
        "streamOpenAIResponses",
        "streamSimpleOpenAIResponses",
        "registerBuiltInApiProviders",
        "resetApiProviders",
    ]


def test_register_builtins_registers_expected_api_set() -> None:
    clear_api_providers()
    register_built_in_api_providers()

    assert {provider.api for provider in get_api_providers()} == {
        "anthropic-messages",
        "openai-completions",
        "mistral-conversations",
        "openai-responses",
        "azure-openai-responses",
        "openai-codex-responses",
        "google-generative-ai",
        "google-vertex",
        "bedrock-converse-stream",
    }


@pytest.mark.asyncio
async def test_create_lazy_stream_converts_loader_failure_to_error_message() -> None:
    stream_fn = register_builtins._create_lazy_stream(_failing_loader)

    result = await stream_fn(_model(), Context(messages=[])).result()

    assert result.stopReason == "error"
    assert result.errorMessage == "load boom"


@pytest.mark.asyncio
async def test_create_lazy_stream_uses_error_message_property_for_loader_failure() -> None:
    class _LoaderError(Exception):
        def __init__(self) -> None:
            super().__init__("preferred message")
            self.message = "preferred message"

        def __str__(self) -> str:
            return "different string"

    async def failing_loader() -> LazyProviderModule:
        raise _LoaderError()

    stream_fn = register_builtins._create_lazy_stream(failing_loader)
    result = await stream_fn(_model(), Context(messages=[])).result()

    assert result.stopReason == "error"
    assert result.errorMessage == "preferred message"


@pytest.mark.asyncio
async def test_create_lazy_stream_converts_sync_stream_factory_failure_to_error_message() -> None:
    def raising_stream(*_args, **_kwargs):
        raise RuntimeError("sync boom")

    async def load_module() -> LazyProviderModule:
        return LazyProviderModule(stream=raising_stream, streamSimple=_unused_simple_stream)

    stream_fn = register_builtins._create_lazy_stream(load_module)
    result = await stream_fn(_model(), Context(messages=[])).result()

    assert result.stopReason == "error"
    assert result.errorMessage == "sync boom"
