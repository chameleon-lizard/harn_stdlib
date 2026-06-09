"""Prompt assembly for the stdlib Harn agent."""

from __future__ import annotations

from pathlib import Path

BASE_SYSTEM_PROMPT = """You are Harn, a terminal coding agent.

Work directly in the user's repository. Prefer reading files before editing.
Use tools when you need local context or must change files. Keep final answers
brief and include the commands or tests you ran. Do not expose secrets.

Tool discipline:
- Use read/ls/find/grep before editing unfamiliar code.
- Use write only for new files or deliberate overwrites.
- Use edit for exact replacements.
- Use bash for local commands and tests.
- Paths are relative to the configured working directory.
"""


def find_agents_file(cwd: Path) -> Path | None:
    """Find the nearest AGENTS.md by walking from cwd to the filesystem root."""

    current = cwd.resolve()
    for directory in (current, *current.parents):
        candidate = directory / "AGENTS.md"
        if candidate.is_file():
            return candidate
    return None


def read_optional_file(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace").strip()


def build_system_prompt(
    cwd: Path,
    extra_system_prompt: str = "",
    agents_file: Path | None = None,
    skills_prompt: str = "",
) -> str:
    """Build the system prompt, including project AGENTS.md when available."""

    resolved_agents_file = agents_file if agents_file is not None else find_agents_file(cwd)
    agents_text = read_optional_file(resolved_agents_file)
    parts = [BASE_SYSTEM_PROMPT.strip()]
    if agents_text:
        parts.append(f"Project instructions from {resolved_agents_file}:\n\n{agents_text}")
    if extra_system_prompt.strip():
        parts.append(f"Additional system instructions:\n\n{extra_system_prompt.strip()}")
    if skills_prompt.strip():
        parts.append(f"Active skill instructions:\n\n{skills_prompt.strip()}")
    return "\n\n---\n\n".join(parts)
