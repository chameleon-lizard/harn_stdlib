"""Tests for prompt template argument parsing and substitution,
ported from prompt-templates.test.ts.

Tests verify argument parsing with quotes and special characters,
placeholder substitution ($1, $2, $@, $ARGUMENTS, ${@:N}, ${@:N:L}),
and that argument values containing patterns are not recursively substituted.
"""

from __future__ import annotations

from harn_coding_agent.core.prompt_templates import parse_command_args, substitute_args


class TestSubstituteArgs:
    """Ported from prompt-templates.test.ts: substituteArgs section."""

    def test_replaces_dollar_arguments_with_all_args_joined(self) -> None:
        assert substitute_args("Test: $ARGUMENTS", ["a", "b", "c"]) == "Test: a b c"

    def test_replaces_dollar_at_with_all_args_joined(self) -> None:
        assert substitute_args("Test: $@", ["a", "b", "c"]) == "Test: a b c"

    def test_dollar_at_and_dollar_arguments_are_identical(self) -> None:
        args = ["foo", "bar", "baz"]
        assert substitute_args("Test: $@", args) == substitute_args("Test: $ARGUMENTS", args)

    def test_does_not_recursively_substitute_patterns_in_argument_values(self) -> None:
        assert substitute_args("$ARGUMENTS", ["$1", "$ARGUMENTS"]) == "$1 $ARGUMENTS"
        assert substitute_args("$@", ["$100", "$1"]) == "$100 $1"
        assert substitute_args("$ARGUMENTS", ["$100", "$1"]) == "$100 $1"

    def test_supports_mixed_numbered_and_dollar_arguments(self) -> None:
        assert substitute_args("$1: $ARGUMENTS", ["prefix", "a", "b"]) == "prefix: prefix a b"

    def test_supports_mixed_numbered_and_dollar_at(self) -> None:
        assert substitute_args("$1: $@", ["prefix", "a", "b"]) == "prefix: prefix a b"

    def test_handles_empty_arguments_array_with_dollar_arguments(self) -> None:
        assert substitute_args("Test: $ARGUMENTS", []) == "Test: "

    def test_handles_empty_arguments_array_with_dollar_at(self) -> None:
        assert substitute_args("Test: $@", []) == "Test: "

    def test_handles_empty_arguments_array_with_dollar_1(self) -> None:
        assert substitute_args("Test: $1", []) == "Test: "

    def test_handles_multiple_occurrences_of_dollar_arguments(self) -> None:
        assert substitute_args("$ARGUMENTS and $ARGUMENTS", ["a", "b"]) == "a b and a b"

    def test_handles_multiple_occurrences_of_dollar_at(self) -> None:
        assert substitute_args("$@ and $@", ["a", "b"]) == "a b and a b"

    def test_handles_special_characters_in_arguments(self) -> None:
        assert substitute_args("$1 $2: $ARGUMENTS", ["arg100", "@user"]) == "arg100 @user: arg100 @user"

    def test_handles_out_of_range_numbered_placeholders(self) -> None:
        assert substitute_args("$1 $2 $3 $4 $5", ["a", "b"]) == "a b   "

    def test_handles_unicode_characters(self) -> None:
        result = substitute_args("$ARGUMENTS", ["\u65e5\u672c\u8a9e", "\U0001f389", "caf\u00e9"])
        assert result == "\u65e5\u672c\u8a9e \U0001f389 caf\u00e9"

    def test_preserves_newlines_and_tabs_in_argument_values(self) -> None:
        assert substitute_args("$1 $2", ["line1\nline2", "tab\tthere"]) == "line1\nline2 tab\tthere"

    def test_handles_consecutive_dollar_patterns(self) -> None:
        assert substitute_args("$1$2", ["a", "b"]) == "ab"

    def test_handles_single_argument_with_dollar_arguments(self) -> None:
        assert substitute_args("Test: $ARGUMENTS", ["only"]) == "Test: only"

    def test_handles_dollar_0(self) -> None:
        assert substitute_args("$0", ["a", "b"]) == ""

    def test_handles_decimal_number_in_pattern(self) -> None:
        assert substitute_args("$1.5", ["a"]) == "a.5"

    def test_handles_non_matching_patterns(self) -> None:
        assert substitute_args("$A $$ $ $ARGS", ["a"]) == "$A $$ $ $ARGS"

    def test_case_sensitive(self) -> None:
        assert substitute_args("$arguments $Arguments $ARGUMENTS", ["a", "b"]) == "$arguments $Arguments a b"

    def test_command_with_no_placeholders(self) -> None:
        assert substitute_args("Just plain text", ["a", "b"]) == "Just plain text"

    def test_command_with_only_placeholders(self) -> None:
        assert substitute_args("$1 $2 $@", ["a", "b", "c"]) == "a b a b c"

    def test_very_long_argument_lists(self) -> None:
        args = [f"arg{i}" for i in range(100)]
        result = substitute_args("$ARGUMENTS", args)
        assert result == " ".join(args)

    def test_numbered_placeholders_with_multiple_digits(self) -> None:
        args = [f"val{i}" for i in range(15)]
        assert substitute_args("$10 $12 $15", args) == "val9 val11 val14"


class TestSubstituteArgsArraySlicing:
    """Ported from prompt-templates.test.ts: array slicing section."""

    def test_slices_from_index(self) -> None:
        assert substitute_args("${@:2}", ["a", "b", "c", "d"]) == "b c d"
        assert substitute_args("${@:1}", ["a", "b", "c"]) == "a b c"
        assert substitute_args("${@:3}", ["a", "b", "c", "d"]) == "c d"

    def test_slices_with_length(self) -> None:
        assert substitute_args("${@:2:2}", ["a", "b", "c", "d"]) == "b c"
        assert substitute_args("${@:1:1}", ["a", "b", "c"]) == "a"
        assert substitute_args("${@:3:1}", ["a", "b", "c", "d"]) == "c"
        assert substitute_args("${@:2:3}", ["a", "b", "c", "d", "e"]) == "b c d"

    def test_handles_out_of_range_slices(self) -> None:
        assert substitute_args("${@:99}", ["a", "b"]) == ""
        assert substitute_args("${@:5}", ["a", "b"]) == ""
        assert substitute_args("${@:10:5}", ["a", "b"]) == ""

    def test_handles_zero_length_slices(self) -> None:
        assert substitute_args("${@:2:0}", ["a", "b", "c"]) == ""
        assert substitute_args("${@:1:0}", ["a", "b"]) == ""

    def test_handles_length_exceeding_array(self) -> None:
        assert substitute_args("${@:2:99}", ["a", "b", "c"]) == "b c"
        assert substitute_args("${@:1:10}", ["a", "b"]) == "a b"

    def test_processes_slice_before_simple_dollar_at(self) -> None:
        assert substitute_args("${@:2} vs $@", ["a", "b", "c"]) == "b c vs a b c"
        assert substitute_args("First: ${@:1:1}, All: $@", ["x", "y", "z"]) == "First: x, All: x y z"

    def test_does_not_recursively_substitute_slice_patterns_in_args(self) -> None:
        assert substitute_args("${@:1}", ["${@:2}", "test"]) == "${@:2} test"
        assert substitute_args("${@:2}", ["a", "${@:3}", "c"]) == "${@:3} c"

    def test_mixed_usage_with_positional_args(self) -> None:
        assert substitute_args("$1: ${@:2}", ["cmd", "arg1", "arg2"]) == "cmd: arg1 arg2"
        assert substitute_args("$1 $2 ${@:3}", ["a", "b", "c", "d"]) == "a b c d"


class TestParseCommandArgs:
    """Ported from prompt-templates.test.ts: parseCommandArgs section."""

    def test_splits_simple_words(self) -> None:
        assert parse_command_args("hello world") == ["hello", "world"]

    def test_handles_quoted_strings(self) -> None:
        assert parse_command_args('"hello world" foo') == ["hello world", "foo"]

    def test_handles_single_quoted_strings(self) -> None:
        assert parse_command_args("'hello world' foo") == ["hello world", "foo"]

    def test_handles_empty_string(self) -> None:
        assert parse_command_args("") == []

    def test_handles_multiple_spaces(self) -> None:
        assert parse_command_args("  a   b  ") == ["a", "b"]

    def test_handles_tab_as_separator(self) -> None:
        assert parse_command_args("a\tb") == ["a", "b"]
