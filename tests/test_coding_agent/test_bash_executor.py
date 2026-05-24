from __future__ import annotations

import os

import pytest
from harnify_coding_agent.core import bash_executor
from harnify_coding_agent.core.tools import truncate as truncate_module


@pytest.mark.asyncio
async def test_execute_bash_with_operations_uses_js_string_length_for_rolling_buffer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bash_executor, "DEFAULT_MAX_BYTES", 3)
    monkeypatch.setattr(truncate_module, "DEFAULT_MAX_BYTES", 100)

    class FakeOperations:
        async def exec(self, command, cwd, options):
            for _ in range(4):
                options["onData"]("😀".encode("utf-8"))
            return {"exitCode": 0}

    result = await bash_executor.executeBashWithOperations("echo", "/tmp", FakeOperations())

    assert result.output == "😀😀😀"
    assert result.exitCode == 0
    assert result.truncated is False
    assert result.fullOutputPath is not None
    assert os.path.exists(result.fullOutputPath)


@pytest.mark.asyncio
async def test_execute_bash_with_operations_replaces_invalid_utf8_and_streams_empty_chunks() -> None:
    streamed: list[str] = []

    class FakeOperations:
        async def exec(self, command, cwd, options):
            options["onData"](b"\xff")
            options["onData"](b"")
            return {"exitCode": 0}

    result = await bash_executor.executeBashWithOperations(
        "echo",
        "/tmp",
        FakeOperations(),
        {"onChunk": streamed.append},
    )

    assert result.output == "\ufffd"
    assert streamed == ["\ufffd", ""]


def test_bash_executor_public_exports_match_ts_surface() -> None:
    assert bash_executor.__all__ == [
        "BashExecutorOptions",
        "BashResult",
        "executeBashWithOperations",
    ]
