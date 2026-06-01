"""Tests for OpenAI-to-Anthropic message transformation, ported from
transform-messages-copilot-openai-to-anthropic.test.ts.

Tests that when a Copilot session migrates from an OpenAI model to an
Anthropic model, thinking blocks are converted to text, thoughtSignatures
are stripped, and orphaned tool calls get synthetic results.
"""

from __future__ import annotations

import re
import time

from harn_ai.types import (
    AssistantMessage,
    Model,
    ModelCost,
    TextContent,
    ThinkingContent,
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


def _ts() -> int:
    return int(time.time() * 1000)


def _anthropic_normalize_tool_call_id(
    tool_call_id: str, _model: Model, _source: AssistantMessage
) -> str:
    """Matches the normalize logic from anthropic.py."""
    normalized = re.sub(r"[^a-zA-Z0-9_-]", "_", tool_call_id)
    return normalized[:64]


def _make_copilot_claude_model() -> Model:
    return Model(
        id="claude-sonnet-4.6",
        name="Claude Sonnet 4.6",
        api="anthropic-messages",
        provider="github-copilot",
        baseUrl="https://api.individual.githubcopilot.com",
        reasoning=True,
        input=["text", "image"],
        cost=ModelCost(input=0, output=0, cacheRead=0, cacheWrite=0),
        contextWindow=128000,
        maxTokens=16000,
    )


def _make_assistant_message(content: list) -> AssistantMessage:
    return AssistantMessage(
        content=content,
        api="openai-responses",
        provider="github-copilot",
        model="gpt-5",
        usage=_make_usage(),
        stopReason="toolUse",
        timestamp=_ts(),
    )


class TestCopilotOpenAIToAnthropicMigration:
    """Ported from transform-messages-copilot-openai-to-anthropic.test.ts."""

    def test_converts_thinking_blocks_to_plain_text_when_source_model_differs(self) -> None:
        model = _make_copilot_claude_model()
        messages = [
            UserMessage(content="hello", timestamp=_ts()),
            AssistantMessage(
                content=[
                    ThinkingContent(
                        thinking="Let me think about this...",
                        thinkingSignature="reasoning_content",
                    ),
                    TextContent(text="Hi there!"),
                ],
                api="openai-completions",
                provider="github-copilot",
                model="gpt-4o",
                usage=_make_usage(),
                stopReason="stop",
                timestamp=_ts(),
            ),
        ]

        result = transform_messages(messages, model, _anthropic_normalize_tool_call_id)
        assistant_msg = next(m for m in result if isinstance(m, AssistantMessage))

        # Thinking block should be converted to text since models differ
        thinking_blocks = [b for b in assistant_msg.content if b.type == "thinking"]
        text_blocks = [b for b in assistant_msg.content if b.type == "text"]
        assert len(thinking_blocks) == 0
        assert len(text_blocks) >= 2

    def test_removes_thought_signature_from_tool_calls_when_migrating(self) -> None:
        model = _make_copilot_claude_model()
        messages = [
            UserMessage(content="run a command", timestamp=_ts()),
            AssistantMessage(
                content=[
                    ToolCall(
                        id="call_123",
                        name="bash",
                        arguments={"command": "ls"},
                        thoughtSignature='{"type":"reasoning.encrypted","id":"call_123","data":"encrypted"}',
                    ),
                ],
                api="openai-responses",
                provider="github-copilot",
                model="gpt-5",
                usage=_make_usage(),
                stopReason="toolUse",
                timestamp=_ts(),
            ),
            ToolResultMessage(
                toolCallId="call_123",
                toolName="bash",
                content=[TextContent(text="output")],
                isError=False,
                timestamp=_ts(),
            ),
        ]

        result = transform_messages(messages, model, _anthropic_normalize_tool_call_id)
        assistant_msg = next(m for m in result if isinstance(m, AssistantMessage))
        tool_call = next(b for b in assistant_msg.content if b.type == "toolCall")

        assert tool_call.thoughtSignature is None

    def test_adds_synthetic_tool_results_for_trailing_orphaned_tool_calls(self) -> None:
        model = _make_copilot_claude_model()
        messages = [
            UserMessage(content="read the file", timestamp=_ts()),
            _make_assistant_message([
                ToolCall(
                    id="call_123|fc_123",
                    name="read",
                    arguments={"path": "README.md"},
                ),
            ]),
        ]

        result = transform_messages(messages, model, _anthropic_normalize_tool_call_id)
        last_message = result[-1]

        assert isinstance(last_message, ToolResultMessage)
        assert last_message.toolCallId == "call_123_fc_123"
        assert last_message.toolName == "read"
        assert last_message.isError is True
        assert last_message.content[0].text == "No result provided"

    def test_adds_synthetic_results_only_for_missing_tool_results(self) -> None:
        model = _make_copilot_claude_model()
        messages = [
            UserMessage(content="run commands", timestamp=_ts()),
            _make_assistant_message([
                ToolCall(id="call_1|fc_1", name="read", arguments={"path": "README.md"}),
                ToolCall(id="call_2|fc_2", name="bash", arguments={"command": "pwd"}),
            ]),
            ToolResultMessage(
                toolCallId="call_1|fc_1",
                toolName="read",
                content=[TextContent(text="done")],
                isError=False,
                timestamp=_ts(),
            ),
        ]

        result = transform_messages(messages, model, _anthropic_normalize_tool_call_id)
        synthetic_results = [
            m for m in result if isinstance(m, ToolResultMessage) and m.isError
        ]

        assert len(synthetic_results) == 1
        assert synthetic_results[0].toolCallId == "call_2_fc_2"
        assert synthetic_results[0].toolName == "bash"
        assert synthetic_results[0].content[0].text == "No result provided"
