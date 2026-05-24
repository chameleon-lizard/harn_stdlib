from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

import harnify_ai.providers.images.openrouter as openrouter
from harnify_ai.types import ImagesContext, ImagesModel, ImagesOptions, ModelCost


class _FakeWithRawResponse:
    def __init__(self, response: Any) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return SimpleNamespace(
            parse=lambda: self._response,
            http_response=SimpleNamespace(status_code=200, headers={"x-test": "1"}),
        )


class _FakeClient:
    def __init__(self, response: Any) -> None:
        self.with_raw_response = _FakeWithRawResponse(response)
        self.chat = SimpleNamespace(completions=self)


def _make_model(output: list[str] | None = None) -> ImagesModel:
    return ImagesModel(
        id="google/gemini-3.1-flash-image-preview",
        name="Gemini 3.1 Flash Image Preview",
        api="openrouter-images",
        provider="openrouter",
        baseUrl="https://openrouter.ai/api/v1",
        input=["text", "image"],
        output=output or ["text", "image"],
        cost=ModelCost(input=0.015, output=0.03, cacheRead=0.01, cacheWrite=0.02),
        headers={"HTTP-Referer": "https://example.com"},
    )


def _make_context() -> ImagesContext:
    return ImagesContext(input=[{"type": "text", "text": "Generate a dog"}])


def _make_response() -> Any:
    return SimpleNamespace(
        id="img-1",
        usage=SimpleNamespace(
            prompt_tokens=12,
            completion_tokens=34,
            prompt_tokens_details=SimpleNamespace(cached_tokens=5, cache_write_tokens=2),
        ),
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="Here is your image.",
                    images=[
                        SimpleNamespace(image_url="data:image/png;base64,ZmFrZS1wbmc="),
                        SimpleNamespace(image_url="data:image/png,not-base64"),
                        SimpleNamespace(image_url="https://example.com/image.png"),
                    ],
                )
            )
        ],
    )


@pytest.mark.asyncio
async def test_generate_images_openrouter_maps_output_callbacks_and_request_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_client_args: dict[str, Any] = {}
    captured_payload: dict[str, Any] | None = None
    captured_response_meta: dict[str, Any] | None = None
    fake_client = _FakeClient(_make_response())

    def fake_create_client(
        model: ImagesModel,
        api_key: str,
        option_headers: dict[str, str] | None = None,
        max_retries: int | None = None,
    ) -> _FakeClient:
        captured_client_args.update(
            {
                "model": model,
                "api_key": api_key,
                "option_headers": option_headers,
                "max_retries": max_retries,
            }
        )
        return fake_client

    def on_payload(payload: dict[str, Any], _model: ImagesModel) -> None:
        nonlocal captured_payload
        captured_payload = payload

    def on_response(meta: dict[str, Any], _model: ImagesModel) -> None:
        nonlocal captured_response_meta
        captured_response_meta = meta

    monkeypatch.setattr(openrouter, "_create_client", fake_create_client)

    output = await openrouter.generate_images_openrouter(
        _make_model(),
        _make_context(),
        ImagesOptions(
            apiKey="test-key",
            headers={"X-Test": "1"},
            timeoutMs=2500,
            maxRetries=7,
            onPayload=on_payload,
            onResponse=on_response,
        ),
    )

    assert output.stopReason == "stop"
    assert output.responseId == "img-1"
    assert [item.type for item in output.output] == ["text", "image"]
    assert output.output[0].text == "Here is your image."
    assert output.output[1].mimeType == "image/png"
    assert output.output[1].data == "ZmFrZS1wbmc="
    assert output.usage is not None
    assert output.usage.input == 7
    assert output.usage.output == 34
    assert output.usage.cacheRead == 3
    assert output.usage.cacheWrite == 2
    assert output.usage.totalTokens == 46
    assert captured_client_args["api_key"] == "test-key"
    assert captured_client_args["option_headers"] == {"X-Test": "1"}
    assert captured_client_args["max_retries"] == 7
    assert captured_payload is not None
    assert captured_payload["modalities"] == ["image", "text"]
    assert fake_client.with_raw_response.calls[0]["timeout"] == 2.5
    assert captured_response_meta == {"status": 200, "headers": {"x-test": "1"}}


@pytest.mark.asyncio
async def test_generate_images_openrouter_returns_aborted_result_for_preaborted_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _FakeClient(_make_response())
    signal = asyncio.Event()
    signal.set()

    monkeypatch.setattr(openrouter, "_create_client", lambda *_args, **_kwargs: fake_client)

    output = await openrouter.generate_images_openrouter(
        _make_model(output=["image"]),
        _make_context(),
        ImagesOptions(apiKey="test-key", signal=signal),
    )

    assert output.stopReason == "aborted"
    assert output.errorMessage == "Request aborted"
    assert fake_client.with_raw_response.calls == []


@pytest.mark.asyncio
async def test_generate_images_openrouter_ignores_missing_or_nonbase64_image_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = SimpleNamespace(
        id="img-2",
        usage=None,
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="Only one valid image.",
                    images=[
                        SimpleNamespace(),
                        SimpleNamespace(image_url=SimpleNamespace(url="data:image/png;base64,dmFsaWQ=")),
                        SimpleNamespace(image_url=SimpleNamespace(url="data:image/png,not-base64")),
                    ],
                )
            )
        ],
    )
    fake_client = _FakeClient(response)

    monkeypatch.setattr(openrouter, "_create_client", lambda *_args, **_kwargs: fake_client)

    output = await openrouter.generate_images_openrouter(
        _make_model(output=["image"]),
        _make_context(),
        ImagesOptions(apiKey="test-key"),
    )

    assert output.stopReason == "stop"
    assert [item.type for item in output.output] == ["text", "image"]
    assert output.output[1].data == "dmFsaWQ="


def test_openrouter_images_module_exports_expected_names() -> None:
    assert openrouter.__all__ == ["generateImagesOpenRouter"]


@pytest.mark.asyncio
async def test_generate_images_openrouter_returns_aborted_result_for_inflight_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()

    class _BlockingWithRawResponse:
        async def create(self, **kwargs: Any) -> Any:
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise

    class _BlockingClient:
        def __init__(self) -> None:
            self.with_raw_response = _BlockingWithRawResponse()
            self.chat = SimpleNamespace(completions=self)

    signal = asyncio.Event()

    monkeypatch.setattr(openrouter, "_create_client", lambda *_args, **_kwargs: _BlockingClient())

    task = asyncio.create_task(
        openrouter.generate_images_openrouter(
            _make_model(output=["image"]),
            _make_context(),
            ImagesOptions(apiKey="test-key", signal=signal),
        )
    )

    await asyncio.wait_for(started.wait(), timeout=1)
    signal.set()
    output = await asyncio.wait_for(task, timeout=1)

    assert output.stopReason == "aborted"
    assert output.errorMessage == "Request aborted"
    assert cancelled.is_set() is True
