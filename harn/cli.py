"""Command-line interface for the stdlib Harn agent."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .agent import Agent, AgentError
from .client import OpenRouterClient, OpenRouterError
from .config import (
    DEFAULT_API_KEY_ENV,
    DEFAULT_BASE_URL,
    DEFAULT_MAX_STEPS,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_TOOLS,
    VERSION,
)


def _read_stdin_if_available() -> str:
    if sys.stdin.isatty():
        return ""
    return sys.stdin.read()


def _load_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _collect_prompt(args: argparse.Namespace) -> str:
    chunks: list[str] = []
    if args.prompt:
        chunks.append(args.prompt)
    if args.prompt_file:
        for item in args.prompt_file:
            path = Path(item)
            chunks.append(f"\n\n<file path=\"{path}\">\n{_load_text_file(path)}\n</file>")

    words: list[str] = []
    for token in args.message:
        if token.startswith("@") and len(token) > 1:
            path = Path(token[1:])
            chunks.append(f"\n\n<file path=\"{path}\">\n{_load_text_file(path)}\n</file>")
        else:
            words.append(token)
    if words:
        chunks.append(" ".join(words))

    stdin_text = _read_stdin_if_available()
    if stdin_text.strip():
        chunks.append(stdin_text)
    return "\n".join(part for part in chunks if part).strip()


def _parse_tools(raw: str | None) -> set[str] | None:
    if not raw:
        return set(DEFAULT_TOOLS)
    if raw.strip().lower() in {"all", "*"}:
        return set(DEFAULT_TOOLS)
    values = {item.strip() for item in raw.split(",") if item.strip()}
    unknown = values - set(DEFAULT_TOOLS)
    if unknown:
        raise argparse.ArgumentTypeError(f"unknown tools: {', '.join(sorted(unknown))}")
    return values


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="harn", description="Stdlib-only OpenRouter coding agent.")
    parser.add_argument("message", nargs="*", help="Prompt text. Tokens like @file are attached as text.")
    parser.add_argument("-p", "--prompt", help="Prompt text.")
    parser.add_argument("--prompt-file", action="append", help="Attach a prompt file. Can be used more than once.")
    parser.add_argument("--system-prompt-file", help="Additional system prompt file.")
    parser.add_argument("--agents-file", help="Explicit AGENTS.md path to load instead of auto-discovery.")
    parser.add_argument("--cwd", default=".", help="Working directory for tools.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"OpenRouter model. Default: {DEFAULT_MODEL}")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="OpenRouter-compatible API base URL.")
    parser.add_argument("--api-key-env", default=DEFAULT_API_KEY_ENV, help="Environment variable containing the API key.")
    parser.add_argument("--api-key", help="API key. Prefer the environment variable so it is not saved in shell history.")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="HTTP timeout in seconds.")
    parser.add_argument("--temperature", type=float, default=0.2, help="Model temperature.")
    parser.add_argument("--max-tokens", type=int, help="Optional response token cap.")
    parser.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS, help="Maximum model/tool loop steps.")
    parser.add_argument("--tools", type=_parse_tools, default=set(DEFAULT_TOOLS), help="Comma-separated tools or 'all'.")
    parser.add_argument("--no-tools", action="store_true", help="Disable tool calls.")
    parser.add_argument("--allow-outside-cwd", action="store_true", help="Allow tools to access paths outside cwd.")
    parser.add_argument("--list-tools", action="store_true", help="List available tools and exit.")
    parser.add_argument("--version", action="store_true", help="Print version and exit.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(VERSION)
        return 0
    if args.list_tools:
        print("\n".join(DEFAULT_TOOLS))
        return 0

    prompt = _collect_prompt(args)
    if not prompt:
        parser.error("provide a prompt, --prompt-file, @file, or stdin")

    cwd = Path(args.cwd).resolve()
    extra_system_prompt = ""
    if args.system_prompt_file:
        extra_system_prompt = _load_text_file(Path(args.system_prompt_file))
    agents_file = Path(args.agents_file).resolve() if args.agents_file else None
    api_key = args.api_key or os.environ.get(args.api_key_env, "")

    client = OpenRouterClient(
        api_key=api_key,
        model=args.model,
        base_url=args.base_url,
        timeout=args.timeout,
    )
    agent = Agent(
        client,
        cwd=cwd,
        tools=args.tools,
        allow_outside_cwd=args.allow_outside_cwd,
        max_steps=args.max_steps,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        no_tools=args.no_tools,
        system_prompt=extra_system_prompt,
        agents_file=agents_file,
    )

    try:
        result = agent.run(prompt)
    except (AgentError, OpenRouterError) as exc:
        print(f"harn: {exc}", file=sys.stderr)
        return 1

    print(result.content)
    return 0

