"""Tool-using coding-agent loop implemented with stdlib data structures."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .client import OpenRouterClient
from .config import DEFAULT_MAX_STEPS
from .prompts import build_system_prompt
from .tools import ToolError, ToolRegistry, parse_tool_arguments


class AgentError(RuntimeError):
    """Raised when the agent loop cannot complete."""


@dataclass
class AgentResult:
    content: str
    steps: int
    tool_calls: int
    messages: list[dict[str, Any]]


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
        self.no_tools = no_tools
        self.system_prompt = build_system_prompt(self.cwd, system_prompt, agents_file)

    def run(self, prompt: str) -> AgentResult:
        """Run the agent until it returns a final answer or max_steps is hit."""

        if self.max_steps <= 0:
            raise AgentError("max_steps must be positive")

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": prompt},
        ]
        tool_schemas = [] if self.no_tools else self.registry.schemas(self.enabled_tools)
        tool_call_count = 0

        for step in range(1, self.max_steps + 1):
            response = self.client.chat(
                messages,
                tools=tool_schemas,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            message = response["choices"][0].get("message", {})
            tool_calls = message.get("tool_calls") or []
            content = message.get("content") or ""

            if not tool_calls:
                if not content.strip():
                    messages.append({"role": "assistant", "content": content})
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
                messages.append({"role": "assistant", "content": content})
                return AgentResult(content=content, steps=step, tool_calls=tool_call_count, messages=messages)

            assistant_message: dict[str, Any] = {"role": "assistant", "content": content, "tool_calls": tool_calls}
            messages.append(assistant_message)

            for tool_call in tool_calls:
                tool_call_count += 1
                function = tool_call.get("function") or {}
                name = function.get("name")
                call_id = tool_call.get("id") or f"tool-{tool_call_count}"
                try:
                    arguments = parse_tool_arguments(function.get("arguments"))
                    output = self.registry.run(str(name), arguments)
                except ToolError as exc:
                    output = f"TOOL_ERROR: {exc}"
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": name,
                        "content": output,
                    }
                )

        raise AgentError(f"Agent reached max_steps={self.max_steps} without a final answer")
