"""Tests for orphaned tool call handling, ported from tool-call-without-result.test.ts.

The TS test is E2E (sends requests to live providers). The Python port
unit-tests the transform_messages() function which inserts synthetic tool
results for orphaned tool calls -- the core fix that the E2E test validates.
"""

from __future__ import annotations

import time

from harn_ai.types import (
    AssistantMessage,
    Model,
    ModelCost,
    TextContent,
    ToolCall,
    ToolResultMessage,
    Usage,
    UsageCost,
    UserMessage,
)
from harn_ai.providers.transform_messages import transform_messages


def _make_usage() -> Usage:
    return Usage(
        input=0,
        output=0,
        cacheRead=0,
        cacheWrite=0,
        totalTokens=0,
        cost=UsageCost(input=0, output=0, cacheRead=0, cacheWrite=0, total=0),
    )


def _make_model() -> Model:
    return Model(
        id="test-model",
        name="Test Model",
        api="openai-completions",
        provider="test-provider",
        baseUrl="https://example.com",
        reasoning=False,
        input=["text"],
        cost=ModelCost(input=0, output=0, cacheRead=0, cacheWrite=0),
        contextWindow=128000,
        maxTokens=4096,
    )


def _ts() -> int:
    return int(time.time() * 1000)


class TestToolCallWithoutResult:
    """Verifies that transform_messages inserts synthetic tool results
    for orphaned tool calls (tool call with no matching tool result)."""

    def test_inserts_synthetic_result_for_trailing_orphaned_tool_call(self) -> None:
        model = _make_model()
        messages = [
            UserMessage(
                content="Calculate 25 * 18 using the calculate tool.",
                timestamp=_ts(),
            ),
            AssistantMessage(
                content=[
                    ToolCall(id="tool-1", name="calculate", arguments={"expression": "25 * 18"}),
                ],
                api="openai-completions",
                provider="test-provider",
                model="test-model",
                usage=_make_usage(),
                stopReason="toolUse",
                timestamp=_ts(),
            ),
            # No tool result follows -- user sends a new message instead
            UserMessage(
                content="Never mind, just tell me what is 2+2?",
                timestamp=_ts(),
            ),
        ]

        result = transform_messages(messages, model)
        # A synthetic tool result should be inserted before the user message
        tool_results = [m for m in result if isinstance(m, ToolResultMessage)]
        assert len(tool_results) == 1
        assert tool_results[0].toolCallId == "tool-1"
        assert tool_results[0].isError is True
        assert tool_results[0].content[0].text == "No result provided"

    def test_does_not_insert_synthetic_result_when_result_is_present(self) -> None:
        model = _make_model()
        messages = [
            UserMessage(
                content="Calculate something",
                timestamp=_ts(),
            ),
            AssistantMessage(
                content=[
                    ToolCall(id="tool-1", name="calculate", arguments={"expression": "1+1"}),
                ],
                api="openai-completions",
                provider="test-provider",
                model="test-model",
                usage=_make_usage(),
                stopReason="toolUse",
                timestamp=_ts(),
            ),
            ToolResultMessage(
                toolCallId="tool-1",
                toolName="calculate",
                content=[TextContent(text="2")],
                isError=False,
                timestamp=_ts(),
            ),
            UserMessage(
                content="Thanks!",
                timestamp=_ts(),
            ),
        ]

        result = transform_messages(messages, model)
        error_results = [m for m in result if isinstance(m, ToolResultMessage) and m.isError]
        assert len(error_results) == 0

    def test_inserts_synthetic_for_missing_result_in_multi_tool_call(self) -> None:
        model = _make_model()
        messages = [
            UserMessage(content="Do two things", timestamp=_ts()),
            AssistantMessage(
                content=[
                    ToolCall(id="tool-1", name="read", arguments={"path": "a.txt"}),
                    ToolCall(id="tool-2", name="bash", arguments={"command": "pwd"}),
                ],
                api="openai-completions",
                provider="test-provider",
                model="test-model",
                usage=_make_usage(),
                stopReason="toolUse",
                timestamp=_ts(),
            ),
            ToolResultMessage(
                toolCallId="tool-1",
                toolName="read",
                content=[TextContent(text="file contents")],
                isError=False,
                timestamp=_ts(),
            ),
            # tool-2 has no result -- user sends new message
            UserMessage(content="Never mind about the second one", timestamp=_ts()),
        ]

        result = transform_messages(messages, model)
        synthetic = [m for m in result if isinstance(m, ToolResultMessage) and m.isError]
        assert len(synthetic) == 1
        assert synthetic[0].toolCallId == "tool-2"
        assert synthetic[0].toolName == "bash"

    def test_skips_aborted_assistant_messages(self) -> None:
        model = _make_model()
        messages = [
            UserMessage(content="Hello", timestamp=_ts()),
            AssistantMessage(
                content=[
                    ToolCall(id="tool-1", name="read", arguments={"path": "a.txt"}),
                ],
                api="openai-completions",
                provider="test-provider",
                model="test-model",
                usage=_make_usage(),
                stopReason="aborted",
                timestamp=_ts(),
            ),
            UserMessage(content="Try again", timestamp=_ts()),
        ]

        result = transform_messages(messages, model)
        # Aborted assistant messages are filtered out entirely
        assistant_msgs = [m for m in result if isinstance(m, AssistantMessage)]
        assert len(assistant_msgs) == 0

    def test_skips_error_assistant_messages(self) -> None:
        model = _make_model()
        messages = [
            UserMessage(content="Hello", timestamp=_ts()),
            AssistantMessage(
                content=[],
                api="openai-completions",
                provider="test-provider",
                model="test-model",
                usage=_make_usage(),
                stopReason="error",
                errorMessage="API error",
                timestamp=_ts(),
            ),
            UserMessage(content="Try again", timestamp=_ts()),
        ]

        result = transform_messages(messages, model)
        assistant_msgs = [m for m in result if isinstance(m, AssistantMessage)]
        assert len(assistant_msgs) == 0
