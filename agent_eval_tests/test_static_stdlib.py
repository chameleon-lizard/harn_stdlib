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
        from harn.agent import AgentTraceEvent
        from harn.tui import (
            InputLine,
            TranscriptEntry,
            append_stream_text,
            collapse_content,
            configure_curses_input,
            input_tail,
            input_view,
            is_control_key,
            render_transcript_lines,
            session_status,
            slash_command_help,
            setup_colors,
            attr_for_role,
            upsert_trace_entry,
            wrap_transcript,
        )

        lines = wrap_transcript([TranscriptEntry("user", "hello world " * 6)], 24)
        self.assertGreater(len(lines), 2)
        self.assertTrue(lines[0].startswith("user> "))
        self.assertEqual("> cdef", input_tail("abcdef", 6))
        display, cursor_col = input_view("abcdef", 6, 6)
        self.assertEqual("> def", display)
        self.assertEqual(5, cursor_col)
        self.assertIn("/reset", slash_command_help())
        self.assertIn("/trace", slash_command_help())
        self.assertIn("/continue", slash_command_help())

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
        display_lines = render_transcript_lines([TranscriptEntry("reasoning", "thinking", True)], 80)
        self.assertEqual("reasoning", display_lines[0].role)

        unicode_line = InputLine()
        unicode_line.insert("привет")
        self.assertEqual("привет", unicode_line.text)
        self.assertEqual(6, unicode_line.cursor)

        entries = [TranscriptEntry("user", "first")]
        upsert_trace_entry(
            entries,
            AgentTraceEvent("assistant", "assistant", "one", event_id="assistant:1", append=True),
            "turn:1",
        )
        upsert_trace_entry(
            entries,
            AgentTraceEvent("assistant", "assistant", " two", event_id="assistant:1", append=True),
            "turn:1",
        )
        entries.append(TranscriptEntry("user", "second"))
        upsert_trace_entry(
            entries,
            AgentTraceEvent("assistant", "assistant", "three", event_id="assistant:1", append=True),
            "turn:2",
        )
        upsert_trace_entry(
            entries,
            AgentTraceEvent("tool", "tool call: bash", "$ false", event_id="tool:1"),
            "turn:2",
        )
        upsert_trace_entry(
            entries,
            AgentTraceEvent("error", "tool call failed: bash", "$ false", event_id="tool:1"),
            "turn:2",
        )
        self.assertEqual(["user", "assistant", "user", "assistant", "error"], [entry.role for entry in entries])
        self.assertEqual("one two", entries[1].content)
        self.assertEqual("three", entries[3].content)
        self.assertEqual("error", entries[4].role)

        class FakeCurses:
            COLOR_WHITE = 7
            COLOR_BLACK = 0
            COLOR_BLUE = 4
            COLOR_GREEN = 2
            COLOR_RED = 1
            A_BOLD = 512

            def __init__(self) -> None:
                self.raw_called = False

            def start_color(self) -> None:
                return None

            def use_default_colors(self) -> None:
                return None

            def init_pair(self, *_: object) -> None:
                return None

            def color_pair(self, value: int) -> int:
                return value

            def curs_set(self, *_: object) -> None:
                return None

            def raw(self) -> None:
                self.raw_called = True

        class FakeWindow:
            def __init__(self) -> None:
                self.keypad_values: list[bool] = []

            def keypad(self, value: bool) -> None:
                self.keypad_values.append(value)

        fake_curses = FakeCurses()
        colors = setup_colors(fake_curses)
        fake_window = FakeWindow()
        configure_curses_input(fake_curses, fake_window)
        self.assertTrue(fake_curses.raw_called)
        self.assertEqual([True], fake_window.keypad_values)
        self.assertEqual(1 | fake_curses.A_BOLD, attr_for_role(fake_curses, colors, "reasoning"))
        self.assertEqual(3 | fake_curses.A_BOLD, attr_for_role(fake_curses, colors, "error"))
        self.assertTrue(is_control_key("\x0f", 15))
        self.assertTrue(is_control_key(15, 15))
        self.assertFalse(is_control_key("o", 15))
        status = session_status(None, [{"role": "user", "content": "abcd"}], [TranscriptEntry("user", "abcd")])
        self.assertIn("session: disabled", status)
        self.assertIn("context_estimate: ~8 tokens", status)

        reasoning_entries: list[TranscriptEntry] = []
        upsert_trace_entry(
            reasoning_entries,
            AgentTraceEvent("reasoning", "reasoning: step 1", "It", event_id="reasoning:1", append=True),
            "turn:1",
        )
        upsert_trace_entry(
            reasoning_entries,
            AgentTraceEvent("reasoning", "reasoning: step 1", " seems", event_id="reasoning:1", append=True),
            "turn:1",
        )
        self.assertEqual("reasoning: step 1\nIt seems", reasoning_entries[0].content)
        upsert_trace_entry(
            reasoning_entries,
            AgentTraceEvent("reasoning", "reasoning: step 1", "It seems done", event_id="reasoning:1", append=True),
            "turn:1",
        )
        self.assertEqual("reasoning: step 1\nIt seems done", reasoning_entries[0].content)
        self.assertEqual("abcdef", append_stream_text("abc", "abcdef"))
        self.assertEqual(
            "reasoning: step 2\nThe command failed with exit_code 127",
            append_stream_text("reasoning: step 2\nThe", "\n command failed\n with exit\n_code\n 127"),
        )

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
        self.assertIn("/continue", output.getvalue())
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

    def test_agent_marks_nonzero_bash_exit_as_error_trace(self) -> None:
        from harn.agent import Agent

        class FailingBashClient:
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
                                                "name": "bash",
                                                "arguments": json.dumps({"command": "exit 7"}),
                                            },
                                        }
                                    ],
                                }
                            }
                        ]
                    }
                return {"choices": [{"message": {"content": "done"}}]}

        with tempfile.TemporaryDirectory() as raw_tmp:
            agent = Agent(FailingBashClient(), cwd=Path(raw_tmp), max_steps=3)  # type: ignore[arg-type]
            result = agent.run("run failing command")

        error_events = [event for event in result.trace if event.kind == "error"]
        self.assertTrue(error_events)
        self.assertTrue(any("exit_code=7" in event.content for event in error_events))
        self.assertFalse([event for event in result.trace if event.kind == "result"])

    def test_client_stream_chat_parses_sse_chunks(self) -> None:
        from harn.client import OpenRouterClient

        class FakeResponse:
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *_: object) -> None:
                return None

            def __iter__(self) -> object:
                return iter(
                    [
                        b": keepalive\n",
                        b"\n",
                        b'data: {"choices":[{"delta":{"content":"he"}}]}\n',
                        b"\n",
                        b'data: {"choices":[{"delta":{"content":"llo"}}]}\n',
                        b"\n",
                        b"data: [DONE]\n",
                        b"\n",
                    ]
                )

        captured: dict[str, object] = {}

        def fake_urlopen(request: object, timeout: int) -> FakeResponse:
            captured["body"] = request.data  # type: ignore[attr-defined]
            captured["timeout"] = timeout
            return FakeResponse()

        client = OpenRouterClient("key", "model", timeout=9)
        with mock.patch("harn.client.urllib.request.urlopen", fake_urlopen):
            chunks = list(client.stream_chat([{"role": "user", "content": "hi"}]))

        payload = json.loads(captured["body"].decode("utf-8"))  # type: ignore[union-attr]
        self.assertTrue(payload["stream"])
        self.assertEqual(9, captured["timeout"])
        self.assertEqual("he", chunks[0]["choices"][0]["delta"]["content"])
        self.assertEqual("llo", chunks[1]["choices"][0]["delta"]["content"])

    def test_agent_streams_text_reasoning_and_tool_calls(self) -> None:
        from harn.agent import Agent, append_stream_chunk, normalize_stream_text, stream_reasoning_delta

        self.assertEqual("It seems", stream_reasoning_delta({"reasoning_details": [{"text": "It"}, {"text": " seems"}]}))
        self.assertEqual("It", stream_reasoning_delta({"reasoning": "It", "reasoning_details": [{"text": "It"}]}))
        self.assertEqual("It seems", append_stream_chunk("It", "It seems"))
        self.assertEqual("The command failed with exit_code 127", normalize_stream_text("The\n command failed\n with exit\n_code\n 127"))
        self.assertEqual("The command failed", append_stream_chunk("The", "\n command failed"))

        class StreamingClient:
            model = "fake"

            def __init__(self) -> None:
                self.calls = 0
                self.kwargs: list[dict[str, Any]] = []

            def stream_chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> object:
                self.calls += 1
                self.kwargs.append(kwargs)
                if self.calls == 1:
                    yield {"choices": [{"delta": {"reasoning": "Need a command.\n"}}]}
                    yield {
                        "choices": [
                            {
                                "delta": {
                                    "tool_calls": [
                                        {
                                            "index": 0,
                                            "id": "call-1",
                                            "type": "function",
                                            "function": {
                                                "name": "bash",
                                                "arguments": json.dumps({"command": "printf 'ok\\n'"}),
                                            },
                                        }
                                    ]
                                },
                                "finish_reason": "tool_calls",
                            }
                        ]
                    }
                    return
                yield {"choices": [{"delta": {"content": "do"}}]}
                yield {"choices": [{"delta": {"content": "ne"}, "finish_reason": "stop"}]}

        events: list[Any] = []
        with tempfile.TemporaryDirectory() as raw_tmp:
            client = StreamingClient()
            agent = Agent(
                client,  # type: ignore[arg-type]
                cwd=Path(raw_tmp),
                max_steps=3,
                reasoning={"enabled": True, "exclude": False},
            )
            result = agent.run_turn(agent.initial_messages(), "go", trace_callback=events.append, stream=True)

        self.assertEqual("done", result.content)
        self.assertEqual(2, client.calls)
        self.assertEqual({"enabled": True, "exclude": False}, client.kwargs[0]["reasoning"])
        self.assertIn("reasoning", [event.kind for event in events])
        self.assertIn("assistant", [event.kind for event in events])
        self.assertIn("tool", [event.kind for event in events])
        self.assertIn("result", [event.kind for event in events])
        self.assertEqual("assistant:2", [event.event_id for event in events if event.kind == "assistant"][0])
        self.assertIn("ok", "\n".join(event.content for event in events))

    def test_session_store_persists_state_and_finds_latest(self) -> None:
        from harn.sessions import SessionStore
        from harn.tui import format_session_choices, recent_sessions, select_continue_session

        with tempfile.TemporaryDirectory() as raw_tmp:
            root = Path(raw_tmp) / "sessions"
            first = SessionStore.create(root=root, metadata={"model": "first"})
            first.save_state(
                [{"role": "system", "content": "one"}],
                [{"role": "system", "content": "entry", "collapsible": False, "event_id": None}],
            )
            first.append_event("system", "entry")

            second = SessionStore.create(root=root, metadata={"model": "second"})
            second.save_state(
                [{"role": "system", "content": "two"}],
                [{"role": "system", "content": "entry2", "collapsible": False, "event_id": None}],
            )
            second.append_event("user", "hello")

            latest = SessionStore.latest(root=root, exclude=second.session_id)
            reopened = SessionStore.open(second.session_id, root=root)
            state = reopened.load_state()
            recent = recent_sessions(root=root)
            choices = format_session_choices(recent)
            selected = select_continue_session("1", recent)

            self.assertEqual(first.session_id, latest.session_id)  # type: ignore[union-attr]
            self.assertEqual("two", state["messages"][0]["content"])
            self.assertTrue((reopened.path / "events.jsonl").is_file())
            self.assertIn("hello", (reopened.path / "transcript.log").read_text(encoding="utf-8"))
            self.assertEqual(second.session_id, recent[0].session_id)
            self.assertIn("1. " + second.session_id, choices)
            self.assertIn("Use /continue <number>", choices)
            self.assertEqual(second.session_id, selected.session_id)

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
