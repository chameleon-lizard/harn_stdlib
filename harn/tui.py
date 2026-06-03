"""Stdlib interactive terminal UI for Harn."""

from __future__ import annotations

import sys
import textwrap
from dataclasses import dataclass
from typing import Callable

from .agent import Agent, AgentError
from .client import OpenRouterError


@dataclass
class TranscriptEntry:
    role: str
    content: str


HELP_TEXT = """Commands:
/help   show this help
/clear  clear the visible transcript
/quit   exit the TUI

Submit a message with Enter. Use Up/Down/PageUp/PageDown to scroll.
"""


def wrap_transcript(entries: list[TranscriptEntry], width: int) -> list[str]:
    """Render transcript entries into display-width text lines."""

    safe_width = max(20, width)
    lines: list[str] = []
    for entry in entries:
        prefix = f"{entry.role}> "
        content = entry.content.rstrip() or "(empty)"
        paragraphs = content.splitlines() or [""]
        first = True
        for paragraph in paragraphs:
            available = max(10, safe_width - (len(prefix) if first else 2))
            wrapped = textwrap.wrap(paragraph, width=available, replace_whitespace=False) or [""]
            for item in wrapped:
                if first:
                    lines.append((prefix + item)[:safe_width])
                    first = False
                else:
                    lines.append(("  " + item)[:safe_width])
        lines.append("")
    return lines


def input_tail(text: str, width: int, prompt: str = "> ") -> str:
    """Return the visible tail of an input line."""

    available = max(1, width - len(prompt))
    return prompt + text[-available:]


def run_line_repl(agent: Agent, *, out: object = sys.stdout, inp: object = sys.stdin) -> int:
    """Fallback interactive mode for terminals without curses."""

    print("Harn TUI fallback. Type /help or /quit.", file=out)
    messages = agent.initial_messages()
    while True:
        try:
            print("> ", end="", file=out, flush=True)
            prompt = inp.readline()
            if prompt == "":
                print("", file=out)
                return 0
            prompt = prompt.rstrip("\n")
        except (EOFError, KeyboardInterrupt):
            print("", file=out)
            return 0
        stripped = prompt.strip()
        if not stripped:
            continue
        if stripped in {"/quit", "/exit", ":q"}:
            return 0
        if stripped == "/help":
            print(HELP_TEXT, file=out)
            continue
        try:
            result = agent.run_turn(messages, prompt)
        except (AgentError, OpenRouterError) as exc:
            print(f"error> {exc}", file=out)
            continue
        messages = result.messages
        print(f"assistant> {result.content}", file=out)


def run_curses_tui(agent: Agent) -> int:
    """Run the full-screen curses TUI."""

    try:
        import curses
    except ImportError:
        return run_line_repl(agent)

    def _main(stdscr: object) -> int:
        curses.curs_set(1)
        stdscr.keypad(True)
        curses.use_default_colors()

        entries = [
            TranscriptEntry("system", "Harn stdlib TUI. Type /help for commands, /quit to exit."),
        ]
        messages = agent.initial_messages()
        input_text = ""
        scroll = 0
        status = "ready"

        def add(role: str, content: str) -> None:
            entries.append(TranscriptEntry(role, content))

        def render() -> None:
            nonlocal scroll
            stdscr.erase()
            height, width = stdscr.getmaxyx()
            transcript_height = max(1, height - 3)
            lines = wrap_transcript(entries, width)
            max_scroll = max(0, len(lines) - transcript_height)
            scroll = max(0, min(scroll, max_scroll))
            visible = lines[scroll : scroll + transcript_height]

            for y, line in enumerate(visible):
                try:
                    stdscr.addstr(y, 0, line[: max(0, width - 1)])
                except curses.error:
                    pass

            status_line = f" {status} | {len(entries)} entries | scroll {scroll}/{max_scroll} "
            try:
                stdscr.addstr(transcript_height, 0, status_line[: max(0, width - 1)], curses.A_REVERSE)
                stdscr.addstr(transcript_height + 1, 0, input_tail(input_text, width)[: max(0, width - 1)])
            except curses.error:
                pass
            stdscr.refresh()

        def submit() -> None:
            nonlocal input_text, messages, scroll, status
            prompt = input_text.strip()
            input_text = ""
            if not prompt:
                return
            if prompt in {"/quit", "/exit", ":q"}:
                raise KeyboardInterrupt
            if prompt == "/clear":
                entries.clear()
                add("system", "Transcript cleared.")
                scroll = 0
                return
            if prompt == "/help":
                add("system", HELP_TEXT)
                scroll = 10**9
                return

            add("user", prompt)
            status = "working..."
            scroll = 10**9
            render()
            try:
                result = agent.run_turn(messages, prompt)
            except (AgentError, OpenRouterError) as exc:
                add("error", str(exc))
                status = "error"
                return
            messages = result.messages
            add("assistant", result.content)
            status = f"done: {result.steps} step(s), {result.tool_calls} tool call(s)"
            scroll = 10**9

        while True:
            render()
            key = stdscr.getch()
            if key in (3, 4):
                return 0
            if key in (10, 13):
                try:
                    submit()
                except KeyboardInterrupt:
                    return 0
                continue
            if key in (curses.KEY_BACKSPACE, 127, 8):
                input_text = input_text[:-1]
                continue
            if key == curses.KEY_UP:
                scroll -= 1
                continue
            if key == curses.KEY_DOWN:
                scroll += 1
                continue
            if key == curses.KEY_PPAGE:
                scroll -= 10
                continue
            if key == curses.KEY_NPAGE:
                scroll += 10
                continue
            if 0 <= key < 256:
                char = chr(key)
                if char.isprintable():
                    input_text += char

    try:
        return int(curses.wrapper(_main))
    except (KeyboardInterrupt, EOFError):
        return 0


def run_tui(agent: Agent, *, runner: Callable[[Agent], int] | None = None) -> int:
    """Run the best available interactive UI."""

    selected_runner = runner or run_curses_tui
    return selected_runner(agent)
