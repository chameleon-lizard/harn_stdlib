"""Stdlib filesystem and shell tools exposed to the language model."""

from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .config import DEFAULT_MAX_OUTPUT_CHARS


class ToolError(RuntimeError):
    """Raised when a tool call cannot be completed."""


def _truncate(text: str, limit: int = DEFAULT_MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[truncated {len(text) - limit} chars]"


def _decode_text(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


@dataclass
class Tool:
    name: str
    description: str
    schema: dict[str, Any]
    handler: Callable[..., str]

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.schema,
            },
        }


class ToolRegistry:
    """Tool registry bound to a working directory."""

    def __init__(self, cwd: Path, *, allow_outside_cwd: bool = False) -> None:
        self.cwd = cwd.resolve()
        self.allow_outside_cwd = allow_outside_cwd
        self._tools = self._build_tools()

    def names(self) -> list[str]:
        return sorted(self._tools)

    def schemas(self, enabled: set[str] | None = None) -> list[dict[str, Any]]:
        names = enabled if enabled is not None else set(self._tools)
        return [self._tools[name].openai_schema() for name in self.names() if name in names]

    def run(self, name: str, arguments: dict[str, Any]) -> str:
        if name not in self._tools:
            raise ToolError(f"Unknown tool: {name}")
        try:
            return self._tools[name].handler(**arguments)
        except TypeError as exc:
            raise ToolError(f"Invalid arguments for {name}: {exc}") from exc

    def _resolve(self, path: str | os.PathLike[str]) -> Path:
        raw = Path(path)
        resolved = raw.resolve() if raw.is_absolute() else (self.cwd / raw).resolve()
        if not self.allow_outside_cwd:
            try:
                resolved.relative_to(self.cwd)
            except ValueError as exc:
                raise ToolError(f"Path is outside cwd: {path}") from exc
        return resolved

    def _read(self, path: str) -> str:
        target = self._resolve(path)
        if not target.exists():
            raise ToolError(f"File not found: {path}")
        if not target.is_file():
            raise ToolError(f"Not a file: {path}")
        return _truncate(target.read_text(encoding="utf-8", errors="replace"))

    def _write(self, path: str, content: str, append: bool = False) -> str:
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with target.open(mode, encoding="utf-8") as handle:
            handle.write(content)
        action = "appended" if append else "wrote"
        return f"{action} {len(content)} chars to {target.relative_to(self.cwd)}"

    def _edit(self, path: str, old: str, new: str, count: int = 1) -> str:
        target = self._resolve(path)
        if not target.is_file():
            raise ToolError(f"Not a file: {path}")
        text = target.read_text(encoding="utf-8", errors="replace")
        if old not in text:
            raise ToolError("Old text was not found")
        replace_count = count if count and count > 0 else text.count(old)
        changed = text.replace(old, new, replace_count)
        target.write_text(changed, encoding="utf-8")
        return f"edited {target.relative_to(self.cwd)} ({replace_count} replacement(s))"

    def _ls(self, path: str = ".") -> str:
        target = self._resolve(path)
        if not target.exists():
            raise ToolError(f"Path not found: {path}")
        if target.is_file():
            return str(target.relative_to(self.cwd))
        rows: list[str] = []
        for child in sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
            suffix = "/" if child.is_dir() else ""
            rows.append(child.name + suffix)
        return _truncate("\n".join(rows))

    def _find(self, pattern: str, root: str = ".", max_results: int = 200) -> str:
        target = self._resolve(root)
        if not target.is_dir():
            raise ToolError(f"Not a directory: {root}")
        matches: list[str] = []
        for path in target.rglob("*"):
            rel = path.relative_to(self.cwd)
            if fnmatch.fnmatch(str(rel), pattern) or fnmatch.fnmatch(path.name, pattern):
                matches.append(str(rel) + ("/" if path.is_dir() else ""))
                if len(matches) >= max_results:
                    break
        return "\n".join(matches)

    def _grep(
        self,
        pattern: str,
        root: str = ".",
        case_sensitive: bool = True,
        max_results: int = 200,
    ) -> str:
        target = self._resolve(root)
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            regex = re.compile(pattern, flags)
        except re.error as exc:
            raise ToolError(f"Invalid regex: {exc}") from exc

        files = [target] if target.is_file() else [path for path in target.rglob("*") if path.is_file()]
        results: list[str] = []
        for path in files:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line_no, line in enumerate(text.splitlines(), start=1):
                if regex.search(line):
                    rel = path.relative_to(self.cwd)
                    results.append(f"{rel}:{line_no}: {line}")
                    if len(results) >= max_results:
                        return _truncate("\n".join(results))
        return _truncate("\n".join(results))

    def _bash(self, command: str, timeout: int = 30) -> str:
        if timeout <= 0 or timeout > 300:
            raise ToolError("timeout must be between 1 and 300 seconds")
        try:
            completed = subprocess.run(
                ["/bin/bash", "-lc", command],
                cwd=self.cwd,
                text=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = _decode_text(exc.stdout or b"")
            stderr = _decode_text(exc.stderr or b"")
            raise ToolError(_truncate(f"command timed out after {timeout}s\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}")) from exc

        stdout = _decode_text(completed.stdout)
        stderr = _decode_text(completed.stderr)
        return _truncate(f"exit_code={completed.returncode}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}")

    def _build_tools(self) -> dict[str, Tool]:
        text_arg = {"type": "string"}
        path_arg = {"type": "string", "description": "Path relative to the agent cwd unless absolute paths are enabled."}
        return {
            "read": Tool(
                "read",
                "Read a UTF-8 text file.",
                {
                    "type": "object",
                    "properties": {"path": path_arg},
                    "required": ["path"],
                    "additionalProperties": False,
                },
                self._read,
            ),
            "write": Tool(
                "write",
                "Create, overwrite, or append to a UTF-8 text file.",
                {
                    "type": "object",
                    "properties": {
                        "path": path_arg,
                        "content": text_arg,
                        "append": {"type": "boolean", "default": False},
                    },
                    "required": ["path", "content"],
                    "additionalProperties": False,
                },
                self._write,
            ),
            "edit": Tool(
                "edit",
                "Replace exact text in a UTF-8 text file.",
                {
                    "type": "object",
                    "properties": {
                        "path": path_arg,
                        "old": text_arg,
                        "new": text_arg,
                        "count": {"type": "integer", "minimum": 0, "default": 1},
                    },
                    "required": ["path", "old", "new"],
                    "additionalProperties": False,
                },
                self._edit,
            ),
            "ls": Tool(
                "ls",
                "List a directory.",
                {
                    "type": "object",
                    "properties": {"path": {"type": "string", "default": "."}},
                    "additionalProperties": False,
                },
                self._ls,
            ),
            "find": Tool(
                "find",
                "Find files by shell-style glob pattern.",
                {
                    "type": "object",
                    "properties": {
                        "pattern": text_arg,
                        "root": {"type": "string", "default": "."},
                        "max_results": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 200},
                    },
                    "required": ["pattern"],
                    "additionalProperties": False,
                },
                self._find,
            ),
            "grep": Tool(
                "grep",
                "Search text files with a Python regular expression.",
                {
                    "type": "object",
                    "properties": {
                        "pattern": text_arg,
                        "root": {"type": "string", "default": "."},
                        "case_sensitive": {"type": "boolean", "default": True},
                        "max_results": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 200},
                    },
                    "required": ["pattern"],
                    "additionalProperties": False,
                },
                self._grep,
            ),
            "bash": Tool(
                "bash",
                "Run a bash command in the agent cwd.",
                {
                    "type": "object",
                    "properties": {
                        "command": text_arg,
                        "timeout": {"type": "integer", "minimum": 1, "maximum": 300, "default": 30},
                    },
                    "required": ["command"],
                    "additionalProperties": False,
                },
                self._bash,
            ),
        }


def parse_tool_arguments(raw: str | dict[str, Any] | None) -> dict[str, Any]:
    """Decode a tool-call arguments payload."""

    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ToolError(f"Tool arguments are not valid JSON: {raw}") from exc
    if not isinstance(data, dict):
        raise ToolError("Tool arguments must decode to an object")
    return data
