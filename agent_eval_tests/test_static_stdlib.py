"""Static and local checks that require no network or external packages."""

from __future__ import annotations

import ast
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HARN_DIR = ROOT / "harn"
HARN_STDLIB_DIR = ROOT / "harn_stdlib"

BANNED_IMPORTS = {
    "aiofiles",
    "anthropic",
    "blessed",
    "boto3",
    "click",
    "filelock",
    "google",
    "httpx",
    "json_repair",
    "jsonlines",
    "jsonschema",
    "markdown_it",
    "mistralai",
    "openai",
    "pathspec",
    "psutil",
    "pydantic",
    "pygments",
    "pytest",
    "rapidfuzz",
    "requests",
    "rich",
    "ruamel",
    "term_image",
    "wcmatch",
    "websockets",
    "wcwidth",
}


class StaticStdlibTests(unittest.TestCase):
    def test_pyproject_declares_no_runtime_dependencies(self) -> None:
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        setup_cfg = (ROOT / "setup.cfg").read_text(encoding="utf-8")
        self.assertIn("dependencies = []", text)
        self.assertNotIn("[tool.uv.workspace]", text)
        self.assertNotIn("[dependency-groups]", text)
        self.assertNotIn("pytest", text)
        self.assertIn('harn = "harn.cli:main"', text)
        self.assertIn('harn-stdlib = "harn.cli:main"', text)
        self.assertIn("harn = harn.cli:main", setup_cfg)
        self.assertIn("harn-stdlib = harn.cli:main", setup_cfg)

    def test_runtime_python_files_do_not_import_known_external_packages(self) -> None:
        offenders: list[str] = []
        for package_dir in (HARN_DIR, HARN_STDLIB_DIR):
            for path in package_dir.glob("*.py"):
                offenders.extend(self._external_import_offenders(path))
        self.assertEqual([], offenders)

    def test_harn_and_harn_stdlib_public_api_match(self) -> None:
        import harn
        import harn_stdlib

        for name in harn.__all__:
            self.assertIs(getattr(harn_stdlib, name), getattr(harn, name))

    def test_harn_and_harn_stdlib_module_entrypoints_match(self) -> None:
        harn_tools = self._run_module("harn", "--list-tools")
        stdlib_tools = self._run_module("harn_stdlib", "--list-tools")
        self.assertEqual(harn_tools.stdout, stdlib_tools.stdout)

        harn_version = self._run_module("harn", "--version")
        stdlib_version = self._run_module("harn_stdlib", "--version")
        self.assertEqual(harn_version.stdout, stdlib_version.stdout)

    def test_original_harn_cli_flags_parse_in_stdlib_mode(self) -> None:
        from harn.cli import _resolve_model, build_parser

        parser = build_parser()
        args = parser.parse_args(
            [
                "--provider",
                "openai",
                "--model",
                "gpt-4o",
                "--thinking",
                "high",
                "--print",
                "hello",
                "--no-tools",
                "-t",
                "read,ls",
                "--offline",
                "--no-context-files",
            ]
        )
        self.assertTrue(args.print_mode)
        self.assertTrue(args.no_tools)
        self.assertTrue(args.offline)
        self.assertTrue(args.no_context_files)
        self.assertEqual({"read", "ls"}, args.tools)
        self.assertEqual("openai/gpt-4o", _resolve_model(args.provider, args.model))

    def test_help_includes_original_harn_compatibility_flags(self) -> None:
        completed = self._run_module("harn", "--help")
        for flag in (
            "--provider",
            "--print",
            "--tui",
            "--thinking",
            "--reasoning",
            "--list-models",
            "--no-context-files",
        ):
            self.assertIn(flag, completed.stdout)

    def test_tui_dispatch_rules(self) -> None:
        from harn.cli import build_parser, should_launch_tui

        parser = build_parser()
        explicit = parser.parse_args(["--tui"])
        self.assertTrue(should_launch_tui(explicit, ""))

        no_tui = parser.parse_args(["--no-tui"])
        self.assertFalse(should_launch_tui(no_tui, ""))

        print_mode = parser.parse_args(["-p"])
        self.assertFalse(should_launch_tui(print_mode, ""))

        with mock.patch("sys.stdin.isatty", return_value=True), mock.patch("sys.stdout.isatty", return_value=True):
            default = parser.parse_args([])
            self.assertTrue(should_launch_tui(default, ""))
            self.assertFalse(should_launch_tui(default, "hello"))

    def test_tui_render_helpers(self) -> None:
        from harn.tui import TranscriptEntry, collapse_content, input_tail, input_view, slash_command_help, wrap_transcript

        lines = wrap_transcript([TranscriptEntry("user", "hello world " * 6)], 24)
        self.assertGreater(len(lines), 2)
        self.assertTrue(lines[0].startswith("user> "))
        self.assertEqual("> cdef", input_tail("abcdef", 6))
        display, cursor_col = input_view("abcdef", 6, 6)
        self.assertEqual("> def", display)
        self.assertEqual(5, cursor_col)
        self.assertIn("/reset", slash_command_help())
        self.assertIn("/trace", slash_command_help())

        collapsed = collapse_content("\n".join(str(item) for item in range(8)))
        self.assertIn("Ctrl+O to expand", collapsed)
        expanded_lines = wrap_transcript([TranscriptEntry("result", "\n".join(str(item) for item in range(8)), True)], 80)
        self.assertTrue(any("Ctrl+O to expand" in line for line in expanded_lines))
        full_lines = wrap_transcript(
            [TranscriptEntry("result", "\n".join(str(item) for item in range(8)), True)],
            80,
            expand_collapsible=True,
        )
        self.assertFalse(any("Ctrl+O to expand" in line for line in full_lines))

    def test_tui_input_line_editing_controls(self) -> None:
        from harn.tui import InputLine

        line = InputLine()
        for char in "abcd":
            line.insert(char)
        line.move_left()
        line.move_left()
        line.insert("X")
        self.assertEqual("abXcd", line.text)
        self.assertEqual(3, line.cursor)

        line.move_start()
        line.move_left()
        self.assertEqual(0, line.cursor)
        line.move_end()
        line.move_right()
        self.assertEqual(len(line.text), line.cursor)

        line = InputLine("hello   world", len("hello   world"))
        line.kill_previous_word()
        self.assertEqual("hello   ", line.text)
        self.assertEqual(len("hello   "), line.cursor)
        line.kill_previous_word()
        self.assertEqual("", line.text)
        self.assertEqual(0, line.cursor)

    def test_tui_line_repl_commands(self) -> None:
        from harn.tui import run_line_repl

        class FakeAgent:
            def initial_messages(self) -> list[dict[str, Any]]:
                return [{"role": "system", "content": "fake"}]

        output = io.StringIO()
        code = run_line_repl(FakeAgent(), out=output, inp=io.StringIO("/help\n/commands\n/quit\n"))  # type: ignore[arg-type]
        self.assertEqual(0, code)
        self.assertIn("Harn TUI fallback", output.getvalue())
        self.assertIn("/clear", output.getvalue())
        self.assertIn("/reset", output.getvalue())
        self.assertIn("/trace", output.getvalue())

    def test_config_file_resolves_runtime_options(self) -> None:
        from harn.cli import build_parser, resolve_runtime_options
        from harn.settings import load_settings

        parser = build_parser()
        with tempfile.TemporaryDirectory() as raw_tmp:
            config_path = Path(raw_tmp) / ".harn" / "harn.json"
            config_path.parent.mkdir()
            config_path.write_text(
                (
                    '{"api_key": "cfg-key", "model": "cfg-model", '
                    '"base_url": "https://example.test/api", "timeout": "7", '
                    '"temperature": "0.4", "max_steps": "3", "max_tokens": "123", '
                    '"reasoning": "enabled"}'
                ),
                encoding="utf-8",
            )
            args = parser.parse_args(["--config", str(config_path), "-p", "hello"])
            with mock.patch.dict(os.environ, {}, clear=True):
                runtime = resolve_runtime_options(args, load_settings(config_path))
        self.assertEqual("cfg-key", runtime["api_key"])
        self.assertEqual("cfg-model", runtime["model"])
        self.assertEqual("https://example.test/api", runtime["base_url"])
        self.assertEqual(7, runtime["timeout"])
        self.assertEqual(0.4, runtime["temperature"])
        self.assertEqual(3, runtime["max_steps"])
        self.assertEqual(123, runtime["max_tokens"])
        self.assertEqual({"enabled": True, "exclude": False}, runtime["reasoning"])

    def test_default_home_config_path_is_loaded_dynamically(self) -> None:
        script = "from harn.settings import load_settings; print(load_settings()['model'])"
        with tempfile.TemporaryDirectory() as raw_tmp:
            config_path = Path(raw_tmp) / ".harn" / "harn.json"
            config_path.parent.mkdir()
            config_path.write_text('{"model": "home-config-model"}', encoding="utf-8")
            env = os.environ.copy()
            env["HOME"] = raw_tmp
            completed = subprocess.run(
                [sys.executable, "-c", script],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("home-config-model", completed.stdout.strip())

    def test_runtime_option_precedence_prefers_cli_then_env_then_config(self) -> None:
        from harn.cli import build_parser, resolve_runtime_options

        parser = build_parser()
        settings = {
            "api_key": "cfg-key",
            "api_key_env": "CUSTOM_KEY",
            "model": "cfg-model",
            "base_url": "https://cfg.example/api",
            "timeout": 1,
        }
        args = parser.parse_args(
            [
                "--api-key",
                "cli-key",
                "--model",
                "cli-model",
                "--base-url",
                "https://cli.example/api",
                "--timeout",
                "9",
                "-p",
                "hello",
            ]
        )
        with mock.patch.dict(
            os.environ,
            {
                "CUSTOM_KEY": "env-key",
                "OPENROUTER_API_KEY": "default-env-key",
                "HARN_MODEL": "env-model",
                "OPENROUTER_BASE_URL": "https://env.example/api",
            },
            clear=True,
        ):
            runtime = resolve_runtime_options(args, settings)
        self.assertEqual("cli-key", runtime["api_key"])
        self.assertEqual("cli-model", runtime["model"])
        self.assertEqual("https://cli.example/api", runtime["base_url"])
        self.assertEqual(9, runtime["timeout"])

        env_args = parser.parse_args(["-p", "hello"])
        with mock.patch.dict(
            os.environ,
            {"CUSTOM_KEY": "env-key", "HARN_MODEL": "env-model", "OPENROUTER_BASE_URL": "https://env.example/api"},
            clear=True,
        ):
            runtime = resolve_runtime_options(env_args, settings)
        self.assertEqual("env-key", runtime["api_key"])
        self.assertEqual("env-model", runtime["model"])
        self.assertEqual("https://env.example/api", runtime["base_url"])

    def test_agent_emits_reasoning_and_tool_result_traces(self) -> None:
        from harn.agent import Agent

        class ReasoningToolClient:
            model = "fake"

            def __init__(self) -> None:
                self.calls = 0
                self.kwargs: list[dict[str, Any]] = []

            def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
                self.calls += 1
                self.kwargs.append(kwargs)
                if self.calls == 1:
                    return {
                        "choices": [
                            {
                                "message": {
                                    "content": "",
                                    "reasoning": "Need to inspect the shell.",
                                    "reasoning_details": [
                                        {"type": "reasoning.summary", "summary": "Will run a small command."}
                                    ],
                                    "tool_calls": [
                                        {
                                            "id": "call-1",
                                            "function": {
                                                "name": "bash",
                                                "arguments": json.dumps({"command": "printf 'alpha\\nbeta\\n'"}),
                                            },
                                        }
                                    ],
                                }
                            }
                        ]
                    }
                return {"choices": [{"message": {"content": "done"}}]}

        with tempfile.TemporaryDirectory() as raw_tmp:
            client = ReasoningToolClient()
            agent = Agent(
                client,  # type: ignore[arg-type]
                cwd=Path(raw_tmp),
                max_steps=3,
                reasoning={"enabled": True, "exclude": False},
            )
            result = agent.run("go")

        self.assertEqual("done", result.content)
        self.assertEqual({"enabled": True, "exclude": False}, client.kwargs[0]["reasoning"])
        self.assertIn("reasoning", [event.kind for event in result.trace])
        self.assertIn("tool", [event.kind for event in result.trace])
        self.assertIn("result", [event.kind for event in result.trace])
        self.assertIn("alpha", "\n".join(event.content for event in result.trace))
        self.assertEqual("Need to inspect the shell.", result.messages[2]["reasoning"])
        self.assertIn("reasoning_details", result.messages[2])

    def test_agent_emits_edit_diff_traces(self) -> None:
        from harn.agent import Agent

        class EditClient:
            model = "fake"

            def __init__(self) -> None:
                self.calls = 0

            def chat(self, messages: list[dict[str, Any]], **_: Any) -> dict[str, Any]:
                self.calls += 1
                if self.calls == 1:
                    return {
                        "choices": [
                            {
                                "message": {
                                    "content": "",
                                    "tool_calls": [
                                        {
                                            "id": "call-1",
                                            "function": {
                                                "name": "edit",
                                                "arguments": json.dumps(
                                                    {"path": "demo.txt", "old": "one\ntwo\n", "new": "one\nthree\n"}
                                                ),
                                            },
                                        }
                                    ],
                                }
                            }
                        ]
                    }
                return {"choices": [{"message": {"content": "edited"}}]}

        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            (tmp / "demo.txt").write_text("one\ntwo\n", encoding="utf-8")
            agent = Agent(EditClient(), cwd=tmp, max_steps=3)  # type: ignore[arg-type]
            result = agent.run("edit it")
            file_text = (tmp / "demo.txt").read_text(encoding="utf-8")

        diffs = [event.content for event in result.trace if event.kind == "diff"]
        self.assertEqual("one\nthree\n", file_text)
        self.assertTrue(diffs)
        self.assertIn("-two", diffs[0])
        self.assertIn("+three", diffs[0])

    def test_agent_continues_after_empty_no_tool_reply(self) -> None:
        from harn.agent import Agent

        class BlankThenFinalClient:
            model = "fake"

            def __init__(self) -> None:
                self.calls = 0

            def chat(self, messages: list[dict[str, Any]], **_: Any) -> dict[str, Any]:
                self.calls += 1
                if self.calls == 1:
                    return {"choices": [{"message": {"content": ""}}]}
                return {"choices": [{"message": {"content": "done"}}]}

        client = BlankThenFinalClient()
        with tempfile.TemporaryDirectory() as raw_tmp:
            agent = Agent(client, cwd=Path(raw_tmp), no_tools=True, max_steps=3)  # type: ignore[arg-type]
            result = agent.run("finish")
        self.assertEqual("done", result.content)
        self.assertEqual(2, client.calls)
        self.assertIn("previous assistant message was empty", result.messages[3]["content"])

    def test_cli_lists_tools_with_system_python(self) -> None:
        completed = self._run_module("harn", "--list-tools")
        for tool in ("read", "write", "edit", "bash", "grep", "find", "ls"):
            self.assertIn(tool, completed.stdout)

    def _external_import_offenders(self, path: Path) -> list[str]:
        offenders: list[str] = []
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".", 1)[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module.split(".", 1)[0]]
            else:
                continue
            for name in names:
                if name in BANNED_IMPORTS:
                    offenders.append(f"{path.name}: {name}")
        return offenders

    def _run_module(self, module: str, *args: str) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            [sys.executable, "-m", module, *args],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return completed


if __name__ == "__main__":
    unittest.main()
