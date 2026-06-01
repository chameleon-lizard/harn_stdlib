"""Tests for RPC JSONL framing, ported from rpc-jsonl.test.ts.

Tests the strict JSONL serializer and line buffer that preserves
Unicode line/paragraph separators inside payloads.
"""

from __future__ import annotations

import json

from harn_coding_agent.modes.rpc.jsonl import JsonlLineBuffer, serialize_json_line


class TestSerializeJsonLine:
    """Ported from rpc-jsonl.test.ts: serializeJsonLine section."""

    def test_serializes_strict_jsonl_without_escaping_unicode_separators(self) -> None:
        line = serialize_json_line({"text": "a\u2028b\u2029c"})

        assert "a\u2028b\u2029c" in line
        assert line.endswith("\n")
        assert json.loads(line.strip()) == {"text": "a\u2028b\u2029c"}


class TestJsonlLineBuffer:
    """Ported from rpc-jsonl.test.ts: attachJsonlLineReader section."""

    def test_splits_on_lf_only_and_preserves_unicode_separators(self) -> None:
        buffer = JsonlLineBuffer()
        line_data = serialize_json_line({"text": "a\u2028b\u2029c"})
        lines = buffer.feed(line_data)
        lines.extend(buffer.end())

        assert len(lines) == 1
        assert json.loads(lines[0]) == {"text": "a\u2028b\u2029c"}

    def test_handles_crlf_delimited_input(self) -> None:
        buffer = JsonlLineBuffer()
        lines = buffer.feed('{"a":1}\r\n{"b":2}\r\n')
        lines.extend(buffer.end())

        assert lines == ['{"a":1}', '{"b":2}']

    def test_emits_final_line_without_trailing_lf(self) -> None:
        buffer = JsonlLineBuffer()
        lines = buffer.feed('{"a":1}')
        lines.extend(buffer.end())

        assert lines == ['{"a":1}']

    def test_handles_incremental_chunks(self) -> None:
        buffer = JsonlLineBuffer()
        lines = buffer.feed('{"a":')
        assert lines == []
        lines = buffer.feed('1}\n')
        assert lines == ['{"a":1}']
        trailing = buffer.end()
        assert trailing == []

    def test_handles_empty_input(self) -> None:
        buffer = JsonlLineBuffer()
        lines = buffer.feed("")
        lines.extend(buffer.end())
        assert lines == []
