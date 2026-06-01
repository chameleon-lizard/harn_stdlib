"""Tests for tool argument validation and JSON-schema coercion, ported from validation.test.ts.

Tests validate_tool_arguments() with plain JSON schemas (not Pydantic models)
to ensure AJV-compatible primitive coercion works correctly.
"""

from __future__ import annotations

import pytest

from harn_ai.types import Tool, ToolCall
from harn_ai.utils.validation import validate_tool_arguments


def _create_tool_call_with_plain_schema(
    schema: dict,
    value: object,
) -> tuple[Tool, ToolCall]:
    """Create a Tool + ToolCall pair wrapping a single 'value' property.

    Mirrors the createToolCallWithPlainSchema helper in the TS test.
    """
    tool = Tool(
        name="echo",
        description="Echo tool",
        parameters={
            "type": "object",
            "properties": {
                "value": schema,
            },
            "required": ["value"],
        },
    )

    tool_call = ToolCall(
        type="toolCall",
        id="tool-1",
        name="echo",
        arguments={"value": value},
    )

    return tool, tool_call


class TestValidateToolArguments:
    """Tests ported from validation.test.ts describe('validateToolArguments')."""

    def test_coerces_serialized_plain_json_schemas_with_ajv_compatible_primitive_rules(
        self,
    ) -> None:
        """Mirrors the 'coerces serialized plain JSON schemas' test case."""
        passing_cases: list[tuple[dict, object, object]] = [
            # (schema, input, expected)
            ({"type": "number"}, "42", 42.0),
            ({"type": "number"}, True, 1),
            ({"type": "number"}, None, 0),
            ({"type": "integer"}, "42", 42),
            ({"type": "boolean"}, "true", True),
            ({"type": "boolean"}, "false", False),
            ({"type": "boolean"}, 1, True),
            ({"type": "boolean"}, 0, False),
            ({"type": "string"}, None, ""),
            ({"type": "string"}, True, "true"),
            ({"type": "null"}, "", None),
            ({"type": "null"}, 0, None),
            ({"type": "null"}, False, None),
            # Union types
            ({"type": ["number", "string"]}, "1", "1"),
            ({"type": ["boolean", "number"]}, "1", 1.0),
        ]

        for schema, input_val, expected in passing_cases:
            tool, tool_call = _create_tool_call_with_plain_schema(schema, input_val)
            result = validate_tool_arguments(tool, tool_call)
            assert result == {"value": expected}, (
                f"For schema={schema}, input={input_val!r}: "
                f"expected {{'value': {expected!r}}}, got {result}"
            )

    def test_rejects_invalid_coercions_for_serialized_plain_json_schemas(self) -> None:
        """Mirrors the 'rejects invalid coercions' test case."""
        failing_cases: list[tuple[dict, object]] = [
            # (schema, input)
            ({"type": "boolean"}, "1"),
            ({"type": "boolean"}, "0"),
            ({"type": "null"}, "null"),
            ({"type": "integer"}, "42.1"),
        ]

        for schema, input_val in failing_cases:
            tool, tool_call = _create_tool_call_with_plain_schema(schema, input_val)
            with pytest.raises(ValueError, match="Validation failed"):
                validate_tool_arguments(tool, tool_call)
