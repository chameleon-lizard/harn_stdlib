"""Command-line interface for the stdlib Harn agent."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

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
from .settings import SettingsError, float_setting, int_setting, load_settings, string_setting
from .skills import SkillError, coerce_skill_names, default_skills_root, discover_skills, format_skill_list
from .tui import run_tui


REASONING_EFFORTS = {"minimal", "low", "medium", "high", "xhigh"}


def _read_stdin_if_available() -> str:
    if sys.stdin.isatty():
        return ""
    return sys.stdin.read()


def _load_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _collect_prompt(args: argparse.Namespace, *, read_stdin: bool = True) -> str:
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

    if read_stdin:
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


def _text_or_file(value: str) -> str:
    path = Path(value)
    if path.is_file():
        return _load_text_file(path)
    return value


def _resolve_model(provider: str | None, model: str) -> str:
    if provider and provider != "openrouter" and "/" not in model:
        return f"{provider}/{model}"
    return model


def _print_models(client: OpenRouterClient, search: str | None) -> int:
    needle = (search or "").lower()
    models = client.list_models()
    rows: list[str] = []
    for model in models:
        model_id = str(model.get("id", ""))
        name = str(model.get("name", ""))
        haystack = f"{model_id} {name}".lower()
        if needle and needle not in haystack:
            continue
        rows.append(model_id if not name or name == model_id else f"{model_id}\t{name}")
    print("\n".join(sorted(rows)))
    return 0


def _setting_path(raw: str | None) -> Path | None:
    return Path(raw).expanduser() if raw else None


def _bool_setting(value: object, name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    raise SettingsError(f"Config setting {name!r} must be a boolean")


def _optional_int(value: object, name: str) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise SettingsError(f"Config setting {name!r} must be an integer") from exc


def _reasoning_from_label(label: str, *, max_tokens: int | None = None) -> dict[str, Any] | None:
    lowered = label.strip().lower()
    if lowered in {"", "auto"}:
        if max_tokens is None:
            return None
        return {"max_tokens": max_tokens, "exclude": False}
    if lowered in {"off", "none", "false", "0"}:
        return {"exclude": True}
    if lowered in {"enabled", "on", "true", "1"}:
        if max_tokens is not None:
            return {"max_tokens": max_tokens, "exclude": False}
        return {"enabled": True, "exclude": False}
    if lowered in REASONING_EFFORTS:
        if max_tokens is not None:
            raise SettingsError("Reasoning effort and reasoning_max_tokens cannot both be set")
        return {"effort": lowered, "exclude": False}
    raise SettingsError(f"Unsupported reasoning setting: {label}")


def _reasoning_from_config(settings: dict[str, object]) -> dict[str, Any] | None:
    max_tokens = _optional_int(settings.get("reasoning_max_tokens"), "reasoning_max_tokens")
    effort = string_setting(settings, "reasoning_effort")
    if effort:
        return _reasoning_from_label(effort, max_tokens=max_tokens)

    raw = settings.get("reasoning")
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, bool):
        return {"enabled": True, "exclude": False} if raw else {"exclude": True}
    if isinstance(raw, str):
        return _reasoning_from_label(raw, max_tokens=max_tokens)
    if raw is not None:
        raise SettingsError("Config setting 'reasoning' must be a string, boolean, or object")
    if max_tokens is not None:
        return {"max_tokens": max_tokens, "exclude": False}

    enabled = settings.get("reasoning_enabled")
    exclude = settings.get("reasoning_exclude")
    if enabled is None and exclude is None:
        return None
    resolved: dict[str, Any] = {}
    if enabled is not None:
        resolved["enabled"] = _bool_setting(enabled, "reasoning_enabled")
    if exclude is not None:
        resolved["exclude"] = _bool_setting(exclude, "reasoning_exclude")
    return resolved


def resolve_reasoning_options(args: argparse.Namespace, settings: dict[str, object]) -> dict[str, Any] | None:
    """Resolve OpenRouter reasoning options from CLI, environment, then config."""

    cli_max_tokens = args.reasoning_max_tokens
    if args.reasoning and args.reasoning != "auto":
        return _reasoning_from_label(args.reasoning, max_tokens=cli_max_tokens)
    if cli_max_tokens is not None:
        return {"max_tokens": cli_max_tokens, "exclude": False}
    if args.thinking:
        return _reasoning_from_label(args.thinking)

    env_reasoning = os.environ.get("HARN_REASONING")
    env_max_tokens = _optional_int(os.environ.get("HARN_REASONING_MAX_TOKENS"), "HARN_REASONING_MAX_TOKENS")
    if env_reasoning:
        return _reasoning_from_label(env_reasoning, max_tokens=env_max_tokens)
    if env_max_tokens is not None:
        return {"max_tokens": env_max_tokens, "exclude": False}

    return _reasoning_from_config(settings)


def resolve_runtime_options(args: argparse.Namespace, settings: dict[str, object]) -> dict[str, object]:
    """Resolve runtime options using CLI, environment, config, then defaults."""

    api_key_env = args.api_key_env or string_setting(settings, "api_key_env") or DEFAULT_API_KEY_ENV
    api_key = (
        args.api_key
        or os.environ.get(api_key_env)
        or string_setting(settings, "api_key", "openrouter_api_key")
        or ""
    )
    model = args.model or os.environ.get("HARN_MODEL") or string_setting(settings, "model") or DEFAULT_MODEL
    base_url = (
        args.base_url
        or os.environ.get("OPENROUTER_BASE_URL")
        or string_setting(settings, "base_url", "openrouter_base_url")
        or DEFAULT_BASE_URL
    )
    timeout = args.timeout if args.timeout is not None else int_setting(settings, "timeout", DEFAULT_TIMEOUT_SECONDS)
    temperature = args.temperature if args.temperature is not None else float_setting(settings, "temperature", 0.2)
    max_steps = args.max_steps if args.max_steps is not None else int_setting(settings, "max_steps", DEFAULT_MAX_STEPS)
    max_tokens = args.max_tokens if args.max_tokens is not None else settings.get("max_tokens")
    if max_tokens is not None:
        try:
            max_tokens = int(max_tokens)
        except (TypeError, ValueError) as exc:
            raise SettingsError("Config setting 'max_tokens' must be an integer") from exc

    return {
        "api_key_env": api_key_env,
        "api_key": api_key,
        "model": _resolve_model(args.provider, str(model)),
        "base_url": str(base_url),
        "timeout": int(timeout),
        "temperature": float(temperature),
        "max_steps": int(max_steps),
        "max_tokens": max_tokens,
        "reasoning": resolve_reasoning_options(args, settings),
    }


def resolve_skills_root(args: argparse.Namespace, settings: dict[str, object]) -> Path:
    """Resolve the skills directory from CLI, env, config, then default."""

    raw = (
        args.skills_dir
        or os.environ.get("HARN_SKILLS_DIR")
        or string_setting(settings, "skills_dir", "skill_dir")
    )
    return Path(raw).expanduser() if raw else default_skills_root()


def resolve_skill_names(args: argparse.Namespace, settings: dict[str, object]) -> list[str]:
    """Resolve active skills from CLI, env, config, then none."""

    if args.no_skills:
        return []
    cli_names: list[str] = []
    for item in args.skill:
        cli_names.extend(coerce_skill_names(item))
    if cli_names:
        return cli_names
    env_names = os.environ.get("HARN_SKILLS")
    if env_names:
        return coerce_skill_names(env_names)
    for key in ("skills", "skill"):
        if key in settings:
            return coerce_skill_names(settings.get(key))
    return []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="harn", description="Stdlib-only OpenRouter coding agent.")
    parser.add_argument("message", nargs="*", help="Prompt text. Tokens like @file are attached as text.")
    parser.add_argument("-p", "--print", dest="print_mode", action="store_true", help="Process prompt and exit.")
    parser.add_argument("--tui", action="store_true", help="Open the stdlib interactive terminal UI.")
    parser.add_argument("--no-tui", action="store_true", help="Disable automatic TUI launch when no prompt is supplied.")
    parser.add_argument("--prompt", help="Prompt text.")
    parser.add_argument("--prompt-file", action="append", help="Attach a prompt file. Can be used more than once.")
    parser.add_argument("--config", help="Config JSON path. Default: ~/.harn/harn.json")
    parser.add_argument("--no-config", action="store_true", help="Do not load ~/.harn/harn.json.")
    parser.add_argument("--provider", help="Provider prefix for OpenRouter model IDs.")
    parser.add_argument("--system-prompt", help="Additional system prompt text.")
    parser.add_argument("--system-prompt-file", help="Additional system prompt file.")
    parser.add_argument("--append-system-prompt", action="append", default=[], help="Append system text or file.")
    parser.add_argument("--agents-file", help="Explicit AGENTS.md path to load instead of auto-discovery.")
    parser.add_argument("--no-context-files", "-nc", action="store_true", help="Disable AGENTS.md discovery.")
    parser.add_argument("--cwd", default=".", help="Working directory for tools.")
    parser.add_argument("--model", help=f"OpenRouter model. Default: {DEFAULT_MODEL}")
    parser.add_argument("--models", help="Accepted for original Harn compatibility; unused in stdlib mode.")
    parser.add_argument("--base-url", help="OpenRouter-compatible API base URL.")
    parser.add_argument(
        "--api-key-env",
        help=f"Environment variable containing the API key. Default: {DEFAULT_API_KEY_ENV}.",
    )
    parser.add_argument("--api-key", help="API key. Prefer the environment variable so it is not saved in shell history.")
    parser.add_argument("--timeout", type=int, help=f"HTTP timeout in seconds. Default: {DEFAULT_TIMEOUT_SECONDS}.")
    parser.add_argument("--temperature", type=float, help="Model temperature.")
    parser.add_argument("--max-tokens", type=int, help="Optional response token cap.")
    parser.add_argument("--max-steps", type=int, help=f"Maximum model/tool loop steps. Default: {DEFAULT_MAX_STEPS}.")
    parser.add_argument(
        "--reasoning",
        choices=["auto", "off", "enabled", "minimal", "low", "medium", "high", "xhigh"],
        help="OpenRouter reasoning control. Default: auto.",
    )
    parser.add_argument("--reasoning-max-tokens", type=int, help="OpenRouter reasoning token budget.")
    parser.add_argument("--tools", "-t", type=_parse_tools, default=set(DEFAULT_TOOLS), help="Comma-separated tools or 'all'.")
    parser.add_argument("--no-tools", "-nt", action="store_true", help="Disable tool calls.")
    parser.add_argument("--no-builtin-tools", "-nbt", action="store_true", help="Disable built-in tools.")
    parser.add_argument("--allow-outside-cwd", action="store_true", help="Allow tools to access paths outside cwd.")
    parser.add_argument("--list-tools", action="store_true", help="List available tools and exit.")
    parser.add_argument("--list-models", nargs="?", const="", help="List OpenRouter models and exit.")
    parser.add_argument("--thinking", choices=["off", "minimal", "low", "medium", "high", "xhigh"], help="Accepted compatibility option.")
    parser.add_argument("--mode", choices=["text", "json", "rpc"], default="text", help="Output mode.")
    parser.add_argument("--continue", "-c", dest="continue_session", action="store_true", help="Accepted compatibility option.")
    parser.add_argument("--resume", "-r", action="store_true", help="Accepted compatibility option.")
    parser.add_argument("--session", help="Accepted compatibility option.")
    parser.add_argument("--fork", help="Accepted compatibility option.")
    parser.add_argument("--session-dir", help="Accepted compatibility option.")
    parser.add_argument("--no-session", action="store_true", help="Accepted compatibility option.")
    parser.add_argument("--export", nargs="*", help="Session export is not available in stdlib mode.")
    parser.add_argument("--extension", "-e", action="append", default=[], help="Accepted compatibility option.")
    parser.add_argument("--no-extensions", "-ne", action="store_true", help="Accepted compatibility option.")
    parser.add_argument("--skill", action="append", default=[], help="Enable a skill by name or path. Can be used more than once.")
    parser.add_argument("--skills-dir", help="Directory containing skills. Default: ~/.harn/skills.")
    parser.add_argument("--list-skills", action="store_true", help="List skills from the skills directory and exit.")
    parser.add_argument("--no-skills", "-ns", action="store_true", help="Disable skills from CLI, environment, and config.")
    parser.add_argument("--prompt-template", action="append", default=[], help="Accepted compatibility option.")
    parser.add_argument("--no-prompt-templates", "-np", action="store_true", help="Accepted compatibility option.")
    parser.add_argument("--theme", action="append", default=[], help="Accepted compatibility option.")
    parser.add_argument("--no-themes", action="store_true", help="Accepted compatibility option.")
    parser.add_argument("--verbose", action="store_true", help="Accepted compatibility option.")
    parser.add_argument("--offline", action="store_true", help="Accepted compatibility option.")
    parser.add_argument("--version", "-v", action="store_true", help="Print version and exit.")
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
    if args.mode == "rpc":
        print("harn: rpc mode is not available in the stdlib runtime", file=sys.stderr)
        return 1
    if args.export is not None:
        print("harn: session export is not available in the stdlib runtime", file=sys.stderr)
        return 1
    try:
        settings = {} if args.no_config else load_settings(_setting_path(args.config))
        runtime = resolve_runtime_options(args, settings)
        skills_root = resolve_skills_root(args, settings)
        skill_names = resolve_skill_names(args, settings)
    except (SettingsError, SkillError) as exc:
        print(f"harn: {exc}", file=sys.stderr)
        return 1
    if args.list_skills:
        print(format_skill_list(discover_skills(skills_root), active_names=skill_names))
        return 0

    prompt = _collect_prompt(args, read_stdin=not args.tui)
    launch_tui = should_launch_tui(args, prompt)
    if launch_tui and args.mode != "text":
        parser.error("--tui only supports --mode text")
    if not prompt and args.list_models is None and not launch_tui:
        parser.error("provide a prompt, --prompt-file, @file, stdin, or run without a prompt to open the TUI")

    cwd = Path(args.cwd).resolve()
    extra_system_prompt_parts: list[str] = []
    if args.system_prompt:
        extra_system_prompt_parts.append(args.system_prompt)
    if args.system_prompt_file:
        extra_system_prompt_parts.append(_load_text_file(Path(args.system_prompt_file)))
    for item in args.append_system_prompt:
        extra_system_prompt_parts.append(_text_or_file(item))
    if args.thinking:
        extra_system_prompt_parts.append(f"Requested thinking level: {args.thinking}.")
    extra_system_prompt = "\n\n".join(extra_system_prompt_parts)

    if args.no_context_files:
        agents_file = Path("/__harn_no_context_files__")
    else:
        agents_file = Path(args.agents_file).resolve() if args.agents_file else None
    client = OpenRouterClient(
        api_key=str(runtime["api_key"]),
        model=str(runtime["model"]),
        base_url=str(runtime["base_url"]),
        timeout=int(runtime["timeout"]),
    )
    if args.list_models is not None:
        try:
            return _print_models(client, args.list_models)
        except OpenRouterError as exc:
            print(f"harn: {exc}", file=sys.stderr)
            return 1

    try:
        agent = Agent(
            client,
            cwd=cwd,
            tools=args.tools,
            allow_outside_cwd=args.allow_outside_cwd,
            max_steps=int(runtime["max_steps"]),
            temperature=float(runtime["temperature"]),
            max_tokens=runtime["max_tokens"],  # type: ignore[arg-type]
            reasoning=runtime["reasoning"],  # type: ignore[arg-type]
            no_tools=args.no_tools or args.no_builtin_tools,
            system_prompt=extra_system_prompt,
            agents_file=agents_file,
            skills_root=skills_root,
            skill_names=skill_names,
        )
    except SkillError as exc:
        print(f"harn: {exc}", file=sys.stderr)
        return 1
    if launch_tui:
        return run_tui(agent)

    try:
        result = agent.run(prompt)
    except (AgentError, OpenRouterError) as exc:
        print(f"harn: {exc}", file=sys.stderr)
        return 1

    if args.mode == "json":
        print(json.dumps({"content": result.content, "steps": result.steps, "tool_calls": result.tool_calls}, ensure_ascii=False))
    else:
        print(result.content)
    return 0


run = main


def should_launch_tui(args: argparse.Namespace, prompt: str) -> bool:
    """Return whether the CLI should enter interactive TUI mode."""

    if args.tui:
        return True
    if args.no_tui or args.print_mode or args.list_models is not None:
        return False
    return not prompt and sys.stdin.isatty() and sys.stdout.isatty()


__all__ = ["build_parser", "main", "run", "should_launch_tui"]
