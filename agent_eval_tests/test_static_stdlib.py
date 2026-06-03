"""Static and local checks that require no network or external packages."""

from __future__ import annotations

import ast
import io
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
        for flag in ("--provider", "--print", "--tui", "--thinking", "--list-models", "--no-context-files"):
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
        from harn.tui import TranscriptEntry, input_tail, wrap_transcript

        lines = wrap_transcript([TranscriptEntry("user", "hello world " * 6)], 24)
        self.assertGreater(len(lines), 2)
        self.assertTrue(lines[0].startswith("user> "))
        self.assertEqual("> cdef", input_tail("abcdef", 6))

    def test_tui_line_repl_commands(self) -> None:
        from harn.tui import run_line_repl

        class FakeAgent:
            def initial_messages(self) -> list[dict[str, Any]]:
                return [{"role": "system", "content": "fake"}]

        output = io.StringIO()
        code = run_line_repl(FakeAgent(), out=output, inp=io.StringIO("/help\n/quit\n"))  # type: ignore[arg-type]
        self.assertEqual(0, code)
        self.assertIn("Harn TUI fallback", output.getvalue())
        self.assertIn("/clear", output.getvalue())

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
