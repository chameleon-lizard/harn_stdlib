"""Tests for CLI argument parsing, ported from args.test.ts.

Tests the parseArgs function which processes command-line arguments into
a structured Args dataclass.
"""

from __future__ import annotations

from harn_coding_agent.cli.args import parse_args


class TestParseArgsVersionFlag:
    def test_parses_version_flag(self) -> None:
        result = parse_args(["--version"])
        assert result.version is True

    def test_parses_v_shorthand(self) -> None:
        result = parse_args(["-v"])
        assert result.version is True

    def test_version_takes_precedence_over_other_args(self) -> None:
        result = parse_args(["--version", "--help", "some message"])
        assert result.version is True
        assert result.help is True
        assert "some message" in result.messages


class TestParseArgsHelpFlag:
    def test_parses_help_flag(self) -> None:
        result = parse_args(["--help"])
        assert result.help is True

    def test_parses_h_shorthand(self) -> None:
        result = parse_args(["-h"])
        assert result.help is True


class TestParseArgsPrintFlag:
    def test_parses_print_flag(self) -> None:
        result = parse_args(["--print"])
        assert result.print is True

    def test_parses_p_shorthand(self) -> None:
        result = parse_args(["-p"])
        assert result.print is True


class TestParseArgsContinueFlag:
    def test_parses_continue_flag(self) -> None:
        result = parse_args(["--continue"])
        assert result.continue_ is True

    def test_parses_c_shorthand(self) -> None:
        result = parse_args(["-c"])
        assert result.continue_ is True


class TestParseArgsResumeFlag:
    def test_parses_resume_flag(self) -> None:
        result = parse_args(["--resume"])
        assert result.resume is True

    def test_parses_r_shorthand(self) -> None:
        result = parse_args(["-r"])
        assert result.resume is True


class TestParseArgsFlagsWithValues:
    def test_parses_provider(self) -> None:
        result = parse_args(["--provider", "openai"])
        assert result.provider == "openai"

    def test_parses_model(self) -> None:
        result = parse_args(["--model", "gpt-4o"])
        assert result.model == "gpt-4o"

    def test_parses_api_key(self) -> None:
        result = parse_args(["--api-key", "sk-test-key"])
        assert result.apiKey == "sk-test-key"

    def test_parses_system_prompt(self) -> None:
        result = parse_args(["--system-prompt", "You are a helpful assistant"])
        assert result.systemPrompt == "You are a helpful assistant"

    def test_parses_append_system_prompt(self) -> None:
        result = parse_args(["--append-system-prompt", "Additional context"])
        assert result.appendSystemPrompt == ["Additional context"]

    def test_parses_multiple_append_system_prompt_flags(self) -> None:
        result = parse_args(["--append-system-prompt", "Context A", "--append-system-prompt", "Context B"])
        assert result.appendSystemPrompt == ["Context A", "Context B"]

    def test_parses_mode(self) -> None:
        result = parse_args(["--mode", "json"])
        assert result.mode == "json"

    def test_parses_mode_rpc(self) -> None:
        result = parse_args(["--mode", "rpc"])
        assert result.mode == "rpc"

    def test_parses_session(self) -> None:
        result = parse_args(["--session", "/path/to/session.jsonl"])
        assert result.session == "/path/to/session.jsonl"

    def test_parses_fork(self) -> None:
        result = parse_args(["--fork", "1234abcd"])
        assert result.fork == "1234abcd"
        assert result.messages == []

    def test_parses_export(self) -> None:
        result = parse_args(["--export", "session.jsonl"])
        assert result.export == "session.jsonl"

    def test_parses_thinking(self) -> None:
        result = parse_args(["--thinking", "high"])
        assert result.thinking == "high"

    def test_parses_models_as_comma_separated_list(self) -> None:
        result = parse_args(["--models", "gpt-4o,claude-sonnet,gemini-pro"])
        assert result.models == ["gpt-4o", "claude-sonnet", "gemini-pro"]


class TestParseArgsNoSessionFlag:
    def test_parses_no_session_flag(self) -> None:
        result = parse_args(["--no-session"])
        assert result.noSession is True


class TestParseArgsToolFlags:
    def test_parses_no_tools_flag(self) -> None:
        result = parse_args(["--no-tools"])
        assert result.noTools is True

    def test_parses_no_builtin_tools_flag(self) -> None:
        result = parse_args(["--no-builtin-tools"])
        assert result.noBuiltinTools is True

    def test_parses_tools_flag(self) -> None:
        result = parse_args(["--tools", "read,bash"])
        assert result.tools == ["read", "bash"]


class TestParseArgsMessagesAndFileArgs:
    def test_parses_plain_text_messages(self) -> None:
        result = parse_args(["hello", "world"])
        assert result.messages == ["hello", "world"]

    def test_parses_at_file_arguments(self) -> None:
        result = parse_args(["@README.md", "@src/main.ts"])
        assert result.fileArgs == ["README.md", "src/main.ts"]

    def test_parses_mixed_messages_and_file_args(self) -> None:
        result = parse_args(["@file.txt", "explain this", "@image.png"])
        assert result.fileArgs == ["file.txt", "image.png"]
        assert result.messages == ["explain this"]


class TestParseArgsComplexCombinations:
    def test_parses_multiple_flags_together(self) -> None:
        result = parse_args([
            "--provider", "anthropic",
            "--model", "claude-sonnet",
            "--print",
            "--thinking", "high",
            "@prompt.md",
            "Do the task",
        ])
        assert result.provider == "anthropic"
        assert result.model == "claude-sonnet"
        assert result.print is True
        assert result.thinking == "high"
        assert result.fileArgs == ["prompt.md"]
        assert result.messages == ["Do the task"]
