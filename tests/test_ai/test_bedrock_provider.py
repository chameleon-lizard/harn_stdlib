from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from harnify_ai.models import get_model
from harnify_ai.providers.amazon_bedrock import (
    build_additional_model_request_fields,
    build_client_settings,
    build_system_prompt,
    convert_messages,
    stream_bedrock,
)
from harnify_ai.types import (
    AssistantMessage,
    Context,
    Model,
    ModelCost,
    TextContent,
    ToolCall,
    ToolResultMessage,
    Usage,
    UsageCost,
    UserMessage,
)


@dataclass(slots=True)
class _UnknownContent:
    type: str = "unknown"
    data: str = "ignored"


class _FakeBedrockClient:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def converse_stream(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return self.response


class _AbortSignal:
    def __init__(self) -> None:
        self.aborted = False
        self._event = asyncio.Event()

    def abort(self) -> None:
        self.aborted = True
        self._event.set()

    def is_set(self) -> bool:
        return self._event.is_set()

    async def wait(self) -> None:
        await self._event.wait()


class _BlockingAsyncStream:
    def __init__(self) -> None:
        self._step = 0
        self.closed = False

    def __aiter__(self) -> _BlockingAsyncStream:
        return self

    async def __anext__(self) -> dict[str, Any]:
        if self._step == 0:
            self._step += 1
            return {"messageStart": {"role": "assistant"}}
        await asyncio.sleep(3600)
        raise StopAsyncIteration

    async def close(self) -> None:
        self.closed = True


def _usage() -> Usage:
    return Usage(
        input=0,
        output=0,
        cacheRead=0,
        cacheWrite=0,
        totalTokens=0,
        cost=UsageCost(input=0, output=0, cacheRead=0, cacheWrite=0, total=0),
    )


def _custom_model(model_id: str, name: str, base_url: str) -> Model:
    return Model(
        id=model_id,
        name=name,
        api="bedrock-converse-stream",
        provider="amazon-bedrock",
        baseUrl=base_url,
        reasoning=True,
        input=["text", "image"],
        cost=ModelCost(input=0, output=0, cacheRead=0, cacheWrite=0),
        contextWindow=200_000,
        maxTokens=32_000,
        thinkingLevelMap={"xhigh": "xhigh", "minimal": "low"},
    )


def test_convert_messages_skips_unknown_blocks_and_merges_tool_results() -> None:
    model = get_model("amazon-bedrock", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
    assert model is not None

    context = Context.model_construct(
        systemPrompt=None,
        messages=[
            UserMessage.model_construct(
                role="user",
                content=[TextContent(text="hello"), _UnknownContent()],
                timestamp=1,
            ),
            AssistantMessage.model_construct(
                role="assistant",
                content=[TextContent(text="working"), _UnknownContent()],
                api=model.api,
                provider=model.provider,
                model=model.id,
                usage=_usage(),
                stopReason="stop",
                timestamp=2,
            ),
            AssistantMessage.model_construct(
                role="assistant",
                content=[ToolCall(id="call_a", name="read", arguments={"path": "a.txt"})],
                api=model.api,
                provider=model.provider,
                model=model.id,
                usage=_usage(),
                stopReason="toolUse",
                timestamp=3,
            ),
            ToolResultMessage(
                toolCallId="call_a",
                toolName="read",
                content=[TextContent(text="alpha")],
                isError=False,
                timestamp=4,
            ),
            ToolResultMessage(
                toolCallId="call_b",
                toolName="read",
                content=[TextContent(text="beta")],
                isError=True,
                timestamp=5,
            ),
        ],
    )

    messages = convert_messages(context, model, "none")

    assert messages[0] == {"role": "user", "content": [{"text": "hello"}]}
    assert messages[1] == {"role": "assistant", "content": [{"text": "working"}]}
    assert messages[2]["content"][0]["toolUse"]["toolUseId"] == "call_a"
    assert messages[3]["role"] == "user"
    assert len(messages[3]["content"]) == 2
    assert messages[3]["content"][0]["toolResult"]["status"] == "success"
    assert messages[3]["content"][1]["toolResult"]["status"] == "error"


def test_application_inference_profile_name_controls_cache_points_and_thinking() -> None:
    model = _custom_model(
        "arn:aws:bedrock:us-east-1:123456789012:application-inference-profile/my-profile",
        "Claude Sonnet 4.6",
        "https://bedrock-runtime.us-east-1.amazonaws.com",
    )

    system_blocks = build_system_prompt("You are helpful.", model, "short")
    converted = convert_messages(
        Context(messages=[{"role": "user", "content": "Hello", "timestamp": 1}]),
        model,
        "short",
    )

    assert system_blocks is not None
    assert system_blocks[1] == {"cachePoint": {"type": "default"}}
    assert converted[-1]["content"][-1] == {"cachePoint": {"type": "default"}}

    adaptive = build_additional_model_request_fields(model, {"reasoning": "high"})
    assert adaptive == {
        "thinking": {"type": "adaptive", "display": "summarized"},
        "output_config": {"effort": "high"},
    }


def test_build_additional_model_request_fields_handles_xhigh_and_govcloud() -> None:
    opus_model = _custom_model(
        "global.anthropic.claude-opus-4-7-v1",
        "Claude Opus 4.7 (Global)",
        "https://bedrock-runtime.us-east-1.amazonaws.com",
    )
    adaptive = build_additional_model_request_fields(opus_model, {"reasoning": "xhigh"})
    assert adaptive == {
        "thinking": {"type": "adaptive", "display": "summarized"},
        "output_config": {"effort": "xhigh"},
    }

    gov_model = _custom_model(
        "us-gov.anthropic.claude-sonnet-4-5-20250929-v1:0",
        "Claude Sonnet 4.5 (GovCloud)",
        "https://bedrock-runtime.us-gov-west-1.amazonaws.com",
    )
    fixed = build_additional_model_request_fields(gov_model, {"reasoning": "high"})
    assert fixed == {
        "thinking": {"type": "enabled", "budget_tokens": 16384},
        "anthropic_beta": ["interleaved-thinking-2025-05-14"],
    }


def test_build_additional_model_request_fields_uses_ts_nullish_defaults() -> None:
    model = get_model("amazon-bedrock", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
    assert model is not None

    fields = build_additional_model_request_fields(
        model,
        {"reasoning": "high", "thinkingDisplay": None, "interleavedThinking": None},
    )

    assert fields == {
        "thinking": {"type": "enabled", "budget_tokens": 16384, "display": "summarized"},
        "anthropic_beta": ["interleaved-thinking-2025-05-14"],
    }


def test_build_client_settings_matches_bedrock_endpoint_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    eu_model = get_model("amazon-bedrock", "eu.anthropic.claude-sonnet-4-5-20250929-v1:0")
    us_model = get_model("amazon-bedrock", "us.anthropic.claude-opus-4-7")
    assert eu_model is not None
    assert us_model is not None

    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    monkeypatch.delenv("AWS_PROFILE", raising=False)

    eu_settings = build_client_settings(eu_model, {"cacheRetention": "none"})
    assert eu_settings.endpoint_url == "https://bedrock-runtime.eu-central-1.amazonaws.com"
    assert eu_settings.region_name == "eu-central-1"

    monkeypatch.setenv("AWS_REGION", "us-east-2")
    us_settings = build_client_settings(us_model, {"cacheRetention": "none"})
    assert us_settings.region_name == "us-east-2"
    assert us_settings.endpoint_url is None

    custom_model = us_model.model_copy(update={"baseUrl": "https://bedrock-vpc.example.com"})
    custom_settings = build_client_settings(custom_model, {"cacheRetention": "none"})
    assert custom_settings.endpoint_url == "https://bedrock-vpc.example.com"
    assert custom_settings.region_name == "us-east-2"


@pytest.mark.asyncio
async def test_stream_bedrock_on_payload_sees_ts_command_shape_before_request_filtering() -> None:
    model = get_model("amazon-bedrock", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
    assert model is not None

    captured_payload: dict[str, Any] | None = None
    fake_client = _FakeBedrockClient(
        {
            "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "req_payload"},
            "stream": [
                {"messageStart": {"role": "assistant"}},
                {"messageStop": {"stopReason": "end_turn"}},
            ],
        }
    )

    def on_payload(payload: dict[str, Any], _model: Model) -> dict[str, Any]:
        nonlocal captured_payload
        captured_payload = payload
        return payload

    stream = stream_bedrock(
        model,
        Context(messages=[{"role": "user", "content": "Hello", "timestamp": 1}]),
        {"client": fake_client, "onPayload": on_payload},
    )
    result = await stream.result()

    assert result.stopReason == "stop"
    assert captured_payload is not None
    assert "system" in captured_payload and captured_payload["system"] is None
    assert "toolConfig" in captured_payload and captured_payload["toolConfig"] is None
    assert "additionalModelRequestFields" in captured_payload and captured_payload["additionalModelRequestFields"] is None
    assert "system" not in fake_client.calls[0]
    assert "toolConfig" not in fake_client.calls[0]
    assert "additionalModelRequestFields" not in fake_client.calls[0]


@pytest.mark.asyncio
async def test_stream_bedrock_maps_converse_stream_events_and_response_metadata() -> None:
    model = get_model("amazon-bedrock", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
    assert model is not None

    response_headers: dict[str, Any] | None = None
    fake_client = _FakeBedrockClient(
        {
            "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "req_123"},
            "stream": [
                {"messageStart": {"role": "assistant"}},
                {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": "Hello"}}},
                {"contentBlockStop": {"contentBlockIndex": 0}},
                {
                    "contentBlockStart": {
                        "contentBlockIndex": 1,
                        "start": {"toolUse": {"toolUseId": "call_1", "name": "calc"}},
                    }
                },
                {"contentBlockDelta": {"contentBlockIndex": 1, "delta": {"toolUse": {"input": '{"a":'}}}},
                {"contentBlockDelta": {"contentBlockIndex": 1, "delta": {"toolUse": {"input": "1}"}}}},
                {"contentBlockStop": {"contentBlockIndex": 1}},
                {"metadata": {"usage": {"inputTokens": 5, "outputTokens": 3, "totalTokens": 8}}},
                {"messageStop": {"stopReason": "tool_use"}},
            ],
        }
    )

    def on_response(payload: dict[str, Any], _model: Model) -> None:
        nonlocal response_headers
        response_headers = payload

    stream = stream_bedrock(
        model,
        Context(messages=[{"role": "user", "content": "Hello", "timestamp": 1}]),
        {"client": fake_client, "onResponse": on_response},
    )

    event_types: list[str] = []
    async for event in stream:
        event_types.append(event.type)

    result = await stream.result()

    assert event_types == [
        "start",
        "text_start",
        "text_delta",
        "text_end",
        "toolcall_start",
        "toolcall_delta",
        "toolcall_delta",
        "toolcall_end",
        "done",
    ]
    assert result.stopReason == "toolUse"
    assert result.content[0].type == "text"
    assert result.content[0].text == "Hello"
    assert result.content[1].type == "toolCall"
    assert result.content[1].name == "calc"
    assert result.content[1].arguments == {"a": 1}
    assert result.usage.input == 5
    assert result.usage.output == 3
    assert result.usage.totalTokens == 8
    assert response_headers == {"status": 200, "headers": {"x-amzn-requestid": "req_123"}}


@pytest.mark.asyncio
async def test_stream_bedrock_aborts_async_stream_iteration_and_closes_stream() -> None:
    model = get_model("amazon-bedrock", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
    assert model is not None

    signal = _AbortSignal()
    blocking_stream = _BlockingAsyncStream()
    fake_client = _FakeBedrockClient(
        {
            "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "req_abort"},
            "stream": blocking_stream,
        }
    )

    async def abort_soon() -> None:
        await asyncio.sleep(0.01)
        signal.abort()

    asyncio.create_task(abort_soon())
    stream = stream_bedrock(
        model,
        Context(messages=[{"role": "user", "content": "Hello", "timestamp": 1}]),
        {"client": fake_client, "signal": signal},
    )

    event_types: list[str] = []
    async for event in stream:
        event_types.append(event.type)

    result = await stream.result()

    assert event_types == ["start", "error"]
    assert result.stopReason == "aborted"
    assert result.errorMessage == "Request was aborted"
    assert blocking_stream.closed is True
