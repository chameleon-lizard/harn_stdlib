"""Tool-using coding-agent loop implemented with stdlib data structures."""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .client import OpenRouterClient
from .config import DEFAULT_MAX_STEPS
from .prompts import build_system_prompt
from .tools import ToolError, ToolRegistry, parse_tool_arguments


class AgentError(RuntimeError):
    """Raised when the agent loop cannot complete."""


@dataclass
class AgentTraceEvent:
    kind: str
    title: str
    content: str
    collapsible: bool = True
    event_id: str | None = None
    append: bool = False


TraceCallback = Callable[[AgentTraceEvent], None]


@dataclass
class AgentResult:
    content: str
    steps: int
    tool_calls: int
    messages: list[dict[str, Any]]
    trace: list[AgentTraceEvent] = field(default_factory=list)


class Agent:
    """A compact OpenRouter-backed coding agent."""

    def __init__(
        self,
        client: OpenRouterClient,
        *,
        cwd: Path,
        tools: set[str] | None = None,
        allow_outside_cwd: bool = False,
        max_steps: int = DEFAULT_MAX_STEPS,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        reasoning: dict[str, Any] | None = None,
        no_tools: bool = False,
        system_prompt: str = "",
        agents_file: Path | None = None,
    ) -> None:
        self.client = client
        self.cwd = cwd.resolve()
        self.registry = ToolRegistry(self.cwd, allow_outside_cwd=allow_outside_cwd)
        self.enabled_tools = tools
        self.max_steps = max_steps
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.reasoning = reasoning
        self.no_tools = no_tools
        self.system_prompt = build_system_prompt(self.cwd, system_prompt, agents_file)

    def run(self, prompt: str) -> AgentResult:
        """Run the agent until it returns a final answer or max_steps is hit."""

        return self.run_turn(self.initial_messages(), prompt)

    def initial_messages(self) -> list[dict[str, Any]]:
        """Return a fresh conversation containing the system prompt."""

        return [{"role": "system", "content": self.system_prompt}]

    def run_turn(
        self,
        messages: list[dict[str, Any]],
        prompt: str,
        *,
        trace_callback: TraceCallback | None = None,
        stream: bool = False,
    ) -> AgentResult:
        """Run one user turn using an existing chat transcript."""

        if self.max_steps <= 0:
            raise AgentError("max_steps must be positive")

        messages = list(messages)
        if not messages:
            messages = self.initial_messages()
        messages.append({"role": "user", "content": prompt})
        tool_schemas = [] if self.no_tools else self.registry.schemas(self.enabled_tools)
        tool_call_count = 0
        trace: list[AgentTraceEvent] = []

        def emit(event: AgentTraceEvent) -> None:
            trace.append(event)
            if trace_callback:
                trace_callback(event)

        for step in range(1, self.max_steps + 1):
            if stream:
                message = self._stream_message(messages, tool_schemas, step, emit)
            else:
                response = self.client.chat(
                    messages,
                    tools=tool_schemas,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    reasoning=self.reasoning,
                )
                message = response["choices"][0].get("message", {})
            tool_calls = message.get("tool_calls") or []
            content = message.get("content") or ""
            reasoning = extract_reasoning_text(message)
            if reasoning and not stream:
                emit(AgentTraceEvent("reasoning", f"reasoning: step {step}", reasoning))

            if not tool_calls:
                if not content.strip():
                    messages.append(build_assistant_message(message, content, tool_calls))
                    if step == self.max_steps:
                        break
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Your previous assistant message was empty. Continue the task by either "
                                "calling the available tools or providing a non-empty final answer."
                            ),
                        }
                    )
                    continue
                messages.append(build_assistant_message(message, content, tool_calls))
                return AgentResult(
                    content=content,
                    steps=step,
                    tool_calls=tool_call_count,
                    messages=messages,
                    trace=trace,
                )

            messages.append(build_assistant_message(message, content, tool_calls))

            for tool_call in tool_calls:
                tool_call_count += 1
                function = tool_call.get("function") or {}
                name = function.get("name")
                call_id = tool_call.get("id") or f"tool-{tool_call_count}"
                try:
                    arguments = parse_tool_arguments(function.get("arguments"))
                    emit(AgentTraceEvent("tool", f"tool call: {name}", format_tool_call(str(name), arguments)))
                    diff = format_tool_diff(str(name), arguments)
                    if diff:
                        emit(AgentTraceEvent("diff", f"diff: {arguments.get('path', name)}", diff))
                    output = self.registry.run(str(name), arguments)
                except ToolError as exc:
                    output = f"TOOL_ERROR: {exc}"
                if output.startswith("TOOL_ERROR:"):
                    emit(AgentTraceEvent("error", f"tool error: {name}", output))
                else:
                    emit(AgentTraceEvent("result", f"tool result: {name}", output))
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": name,
                        "content": output,
                    }
                )

        raise AgentError(f"Agent reached max_steps={self.max_steps} without a final answer")

    def _stream_message(
        self,
        messages: list[dict[str, Any]],
        tool_schemas: list[dict[str, Any]],
        step: int,
        emit: TraceCallback,
    ) -> dict[str, Any]:
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        reasoning_details: list[dict[str, Any]] = []
        tool_states: dict[int, dict[str, Any]] = {}
        finish_reason = ""

        for chunk in self.client.stream_chat(
            messages,
            tools=tool_schemas,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            reasoning=self.reasoning,
        ):
            choices = chunk.get("choices") or []
            if not choices:
                continue
            choice = choices[0]
            finish_reason = str(choice.get("finish_reason") or finish_reason)
            delta = choice.get("delta") or {}
            if not isinstance(delta, dict):
                continue

            content_delta = delta.get("content")
            if isinstance(content_delta, str) and content_delta:
                content_parts.append(content_delta)
                emit(
                    AgentTraceEvent(
                        "assistant",
                        "assistant",
                        content_delta,
                        collapsible=False,
                        event_id=f"assistant:{step}",
                        append=True,
                    )
                )

            direct_reasoning_delta = stream_direct_reasoning_delta(delta)
            if direct_reasoning_delta:
                reasoning_parts.append(direct_reasoning_delta)

            reasoning_delta = stream_reasoning_delta(delta)
            if reasoning_delta:
                emit(
                    AgentTraceEvent(
                        "reasoning",
                        f"reasoning: step {step}",
                        reasoning_delta,
                        event_id=f"reasoning:{step}",
                        append=True,
                    )
                )

            details = delta.get("reasoning_details")
            if isinstance(details, list):
                for detail in details:
                    if isinstance(detail, dict):
                        reasoning_details.append(detail)

            for raw_tool_call in delta.get("tool_calls") or []:
                merge_tool_call_delta(tool_states, raw_tool_call)

        if finish_reason == "error":
            raise AgentError("OpenRouter stream ended with finish_reason=error")

        message: dict[str, Any] = {"content": "".join(content_parts)}
        if reasoning_parts:
            message["reasoning"] = "".join(reasoning_parts)
        if reasoning_details:
            message["reasoning_details"] = reasoning_details
        tool_calls = finalize_streamed_tool_calls(tool_states)
        if tool_calls:
            message["tool_calls"] = tool_calls
        return message


def build_assistant_message(message: dict[str, Any], content: str, tool_calls: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a conversation message while preserving provider reasoning fields."""

    assistant_message: dict[str, Any] = {"role": "assistant", "content": content}
    if tool_calls:
        assistant_message["tool_calls"] = tool_calls
    for key in ("reasoning", "reasoning_content", "reasoning_details"):
        value = message.get(key)
        if value is not None:
            assistant_message[key] = value
    return assistant_message


def extract_reasoning_text(message: dict[str, Any]) -> str:
    """Extract OpenRouter reasoning text from normalized response fields."""

    parts: list[str] = []
    for key in ("reasoning", "reasoning_content"):
        text = reasoning_value_to_text(message.get(key))
        if text:
            parts.append(text)

    details = message.get("reasoning_details")
    if isinstance(details, list):
        for detail in details:
            text = reasoning_detail_to_text(detail)
            if text:
                parts.append(text)
    return "\n\n".join(parts)


def reasoning_value_to_text(value: object) -> str:
    """Convert a provider reasoning field to display text."""

    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        items = [reasoning_value_to_text(item) for item in value]
        return "\n".join(item for item in items if item)
    if isinstance(value, dict):
        return reasoning_detail_to_text(value)
    return str(value).strip()


def reasoning_detail_to_text(detail: object) -> str:
    """Convert one reasoning_details item to display text."""

    if not isinstance(detail, dict):
        return reasoning_value_to_text(detail)
    detail_type = str(detail.get("type") or "reasoning")
    for key in ("text", "summary", "content"):
        value = detail.get(key)
        text = reasoning_value_to_text(value)
        if text:
            return f"[{detail_type}] {text}"
    if detail.get("data") is not None:
        return f"[{detail_type}] encrypted or redacted reasoning block"
    return f"[{detail_type}] {json.dumps(detail, ensure_ascii=False)}"


def stream_reasoning_delta(delta: dict[str, Any]) -> str:
    """Extract visible reasoning text from a streaming delta."""

    parts: list[str] = []
    direct = stream_direct_reasoning_delta(delta)
    if direct:
        parts.append(direct)
    details = delta.get("reasoning_details")
    if isinstance(details, list):
        for detail in details:
            text = reasoning_detail_to_text(detail)
            if text:
                parts.append(text)
    return "\n".join(parts)


def stream_direct_reasoning_delta(delta: dict[str, Any]) -> str:
    """Extract only direct streaming reasoning text fields."""

    parts: list[str] = []
    for key in ("reasoning", "reasoning_content"):
        text = reasoning_value_to_text(delta.get(key))
        if text:
            parts.append(text)
    return "\n".join(parts)


def merge_tool_call_delta(tool_states: dict[int, dict[str, Any]], raw_tool_call: object) -> None:
    """Merge one OpenAI-compatible streaming tool_call delta."""

    if not isinstance(raw_tool_call, dict):
        return
    index = raw_tool_call.get("index", len(tool_states))
    try:
        tool_index = int(index)
    except (TypeError, ValueError):
        tool_index = len(tool_states)

    state = tool_states.setdefault(tool_index, {"function": {"name": "", "arguments": ""}})
    if raw_tool_call.get("id"):
        state["id"] = raw_tool_call["id"]
    if raw_tool_call.get("type"):
        state["type"] = raw_tool_call["type"]

    function = raw_tool_call.get("function")
    if isinstance(function, dict):
        state_function = state.setdefault("function", {"name": "", "arguments": ""})
        if function.get("name"):
            state_function["name"] = str(state_function.get("name") or "") + str(function["name"])
        if function.get("arguments"):
            state_function["arguments"] = str(state_function.get("arguments") or "") + str(function["arguments"])


def finalize_streamed_tool_calls(tool_states: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    """Return complete tool_call objects sorted by stream index."""

    tool_calls: list[dict[str, Any]] = []
    for index in sorted(tool_states):
        state = tool_states[index]
        function = state.get("function") if isinstance(state.get("function"), dict) else {}
        tool_calls.append(
            {
                "id": state.get("id") or f"tool-{index}",
                "type": state.get("type") or "function",
                "function": {
                    "name": function.get("name") or "",
                    "arguments": function.get("arguments") or "",
                },
            }
        )
    return tool_calls


def format_tool_call(name: str, arguments: dict[str, Any]) -> str:
    """Format a tool call for trace display."""

    if name == "bash":
        command = str(arguments.get("command", ""))
        timeout = arguments.get("timeout")
        suffix = f"\ntimeout: {timeout}s" if timeout is not None else ""
        return f"$ {command}{suffix}"
    if name == "edit":
        return f"edit {arguments.get('path', '')}"
    if name == "write":
        content = str(arguments.get("content", ""))
        mode = "append" if arguments.get("append") else "write"
        return f"{mode} {arguments.get('path', '')} ({len(content)} chars)"
    return json.dumps(arguments, ensure_ascii=False, indent=2, sort_keys=True)


def format_tool_diff(name: str, arguments: dict[str, Any]) -> str:
    """Return a compact unified diff for edit-style tool calls."""

    if name != "edit":
        return ""
    old = arguments.get("old")
    new = arguments.get("new")
    path = str(arguments.get("path", "edit"))
    if not isinstance(old, str) or not isinstance(new, str):
        return ""
    return "\n".join(
        difflib.unified_diff(
            old.splitlines(),
            new.splitlines(),
            fromfile=f"{path}:old",
            tofile=f"{path}:new",
            lineterm="",
        )
    )
