from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest

import harnify_ai.providers.openai_responses as openai_responses
from harnify_ai.models import get_model
from harnify_ai.providers.openai_responses import build_params, stream_openai_responses
from harnify_ai.types import Context, Model, ModelCost, Usage, UsageCost


def _openai_model() -> Model:
    model = get_model("openai", "gpt-4o-mini")
    assert model is not None
    return model.model_copy(update={"api": "openai-responses"})


def _reasoning_model() -> Model:
    return Model(
        id="gpt-5.5",
        name="GPT-5.5",
        api="openai-responses",
        provider="openai",
        baseUrl="https://api.openai.com/v1",
        reasoning=True,
        input=["text"],
        cost=ModelCost(input=0, output=0, cacheRead=0, cacheWrite=0),
        contextWindow=200_000,
        maxTokens=8_192,
    )


def _usage() -> Usage:
    return Usage(
        input=0,
        output=0,
        cacheRead=0,
        cacheWrite=0,
        totalTokens=0,
        cost=UsageCost(input=0, output=0, cacheRead=0, cacheWrite=0, total=0),
    )


class _FakeResponseStream:
    def __init__(self, events: list[dict[str, object]]) -> None:
        self._events = list(events)
        self.closed = False

    def __aiter__(self) -> _FakeResponseStream:
        return self

    async def __anext__(self) -> dict[str, object]:
        if not self._events:
            raise StopAsyncIteration
        return self._events.pop(0)

    async def close(self) -> None:
        self.closed = True


class _BlockingResponseStream:
    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.closed = False
        self.cancelled = False

    def __aiter__(self) -> _BlockingResponseStream:
        return self

    async def __anext__(self) -> dict[str, object]:
        self.entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        raise StopAsyncIteration

    async def close(self) -> None:
        self.closed = True


class _RawResponse:
    def __init__(self, parsed: object) -> None:
        self.http_response = httpx.Response(
            202,
            headers={"x-request-id": "resp-123"},
            request=httpx.Request("POST", "https://api.example.test/v1/responses"),
        )
        self._parsed = parsed

    async def parse(self) -> object:
        return self._parsed


class _WithRawResponse:
    def __init__(self, raw_response: _RawResponse) -> None:
        self.raw_response = raw_response
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs: object) -> _RawResponse:
        self.calls.append(dict(kwargs))
        return self.raw_response


class _FakeClientWithOptions:
    def __init__(self, raw_response: _RawResponse) -> None:
        self.with_options_calls: list[dict[str, object]] = []
        self.responses = type("Responses", (), {"with_raw_response": _WithRawResponse(raw_response)})()

    def with_options(self, **kwargs: object) -> _FakeClientWithOptions:
        self.with_options_calls.append(dict(kwargs))
        return self


def test_build_params_uses_ts_truthiness_for_max_tokens() -> None:
    params = build_params(
        _reasoning_model(),
        Context(messages=[{"role": "user", "content": "hi", "timestamp": 1}]),
        {"maxTokens": 0},
    )

    assert "max_output_tokens" not in params


def test_build_params_matches_ts_default_off_reasoning_semantics() -> None:
    base_model = _reasoning_model()
    context = Context(messages=[{"role": "user", "content": "hi", "timestamp": 1}])

    params_without_map = build_params(base_model, context)
    assert params_without_map["reasoning"] == {"effort": "none"}

    params_without_off_key = build_params(base_model.model_copy(update={"thinkingLevelMap": {}}), context)
    assert params_without_off_key["reasoning"] == {"effort": "none"}

    params_with_empty_off = build_params(
        base_model.model_copy(update={"thinkingLevelMap": {"off": ""}}),
        context,
    )
    assert params_with_empty_off["reasoning"] == {"effort": ""}

    params_with_null_off = build_params(
        base_model.model_copy(update={"thinkingLevelMap": {"off": None}}),
        context,
    )
    assert "reasoning" not in params_with_null_off


@pytest.mark.asyncio
async def test_stream_openai_responses_applies_request_timeout_retries_and_on_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _openai_model()
    context = Context(messages=[{"role": "user", "content": "hi", "timestamp": 1}])
    raw_response = _RawResponse(
        _FakeResponseStream(
            [
                {
                    "type": "response.completed",
                    "response": {
                        "id": "resp_1",
                        "status": "completed",
                        "usage": {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
                    },
                }
            ]
        )
    )
    fake_client = _FakeClientWithOptions(raw_response)
    captured: dict[str, object] = {}

    async def on_response(metadata: dict[str, object], response_model: Model) -> None:
        captured["metadata"] = metadata
        captured["model"] = response_model

    monkeypatch.setattr(openai_responses, "create_client", lambda *_args, **_kwargs: fake_client)

    result = await stream_openai_responses(
        model,
        context,
        {"timeoutMs": 2500, "maxRetries": 7, "onResponse": on_response},
    ).result()

    assert fake_client.with_options_calls == [{"timeout": 2.5, "max_retries": 7}]
    assert fake_client.responses.with_raw_response.calls == [build_params(model, context)]
    assert captured["metadata"] == {"status": 202, "headers": {"x-request-id": "resp-123"}}
    assert captured["model"].provider == "openai"
    assert result.responseId == "resp_1"
    assert result.stopReason == "stop"
    assert result.usage.input == 3
    assert result.usage.output == 2


@pytest.mark.asyncio
async def test_stream_openai_responses_short_circuits_preaborted_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signal = asyncio.Event()
    signal.set()
    fake_client = _FakeClientWithOptions(_RawResponse(_FakeResponseStream([])))
    monkeypatch.setattr(openai_responses, "create_client", lambda *_args, **_kwargs: fake_client)

    result = await stream_openai_responses(
        _openai_model(),
        Context(messages=[{"role": "user", "content": "hi", "timestamp": 1}]),
        {"signal": signal},
    ).result()

    assert fake_client.responses.with_raw_response.calls == []
    assert result.stopReason == "aborted"
    assert result.errorMessage == "Request was aborted"


@pytest.mark.asyncio
async def test_stream_openai_responses_aborts_while_waiting_for_stream_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signal = asyncio.Event()
    blocking_stream = _BlockingResponseStream()
    fake_client = _FakeClientWithOptions(_RawResponse(blocking_stream))
    monkeypatch.setattr(openai_responses, "create_client", lambda *_args, **_kwargs: fake_client)

    stream = stream_openai_responses(
        _openai_model(),
        Context(messages=[{"role": "user", "content": "hi", "timestamp": 1}]),
        {"signal": signal},
    )
    await asyncio.wait_for(blocking_stream.entered.wait(), timeout=1)
    signal.set()

    result = await asyncio.wait_for(stream.result(), timeout=1)

    assert result.stopReason == "aborted"
    assert result.errorMessage == "Request was aborted"
    assert blocking_stream.closed is True
    assert blocking_stream.cancelled is True
