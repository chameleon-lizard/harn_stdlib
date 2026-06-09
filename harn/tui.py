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


@dataclass
class InputLine:
    """Editable single-line input state."""

    text: str = ""
    cursor: int = 0

    def insert(self, value: str) -> None:
        self.text = self.text[: self.cursor] + value + self.text[self.cursor :]
        self.cursor += len(value)

    def backspace(self) -> None:
        if self.cursor <= 0:
            return
        self.text = self.text[: self.cursor - 1] + self.text[self.cursor :]
        self.cursor -= 1

    def delete(self) -> None:
        if self.cursor >= len(self.text):
            return
        self.text = self.text[: self.cursor] + self.text[self.cursor + 1 :]

    def move_left(self) -> None:
        self.cursor = max(0, self.cursor - 1)

    def move_right(self) -> None:
        self.cursor = min(len(self.text), self.cursor + 1)

    def move_start(self) -> None:
        self.cursor = 0

    def move_end(self) -> None:
        self.cursor = len(self.text)

    def kill_previous_word(self) -> None:
        if self.cursor <= 0:
            return
        start = self.cursor
        while start > 0 and self.text[start - 1].isspace():
            start -= 1
        while start > 0 and not self.text[start - 1].isspace():
            start -= 1
        self.text = self.text[:start] + self.text[self.cursor :]
        self.cursor = start

    def clear(self) -> None:
        self.text = ""
        self.cursor = 0


SLASH_COMMANDS = (
    ("/help", "show help and key bindings"),
    ("/commands", "list slash commands"),
    ("/clear", "clear the visible transcript"),
    ("/reset", "reset conversation memory"),
    ("/status", "show model, cwd, and loop settings"),
    ("/tools", "show enabled local tools"),
    ("/quit", "exit the TUI"),
)


HELP_TEXT = """Slash commands:
/help      show this help
/commands  list slash commands
/clear     clear the visible transcript
/reset     reset conversation memory
/status    show model, cwd, and loop settings
/tools     show enabled local tools
/quit      exit the TUI

Keys:
Enter submits a message.
Left/Right move the cursor.
Ctrl+A/Ctrl+E move to start/end.
Ctrl+W deletes the previous word.
Ctrl+L redraws the screen.
Up/Down/PageUp/PageDown scroll the transcript.
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


def input_view(text: str, cursor: int, width: int, prompt: str = "> ") -> tuple[str, int]:
    """Return visible input text and the terminal cursor column."""

    safe_width = max(len(prompt) + 2, width)
    safe_cursor = max(0, min(cursor, len(text)))
    available = max(1, safe_width - len(prompt) - 1)
    if safe_cursor <= available:
        start = 0
    else:
        start = safe_cursor - available
    visible = text[start : start + available]
    cursor_col = len(prompt) + safe_cursor - start
    return prompt + visible, max(0, min(cursor_col, safe_width - 1))


def slash_command_help() -> str:
    """Return a formatted slash command list."""

    width = max(len(name) for name, _description in SLASH_COMMANDS)
    rows = [f"{name:<{width}}  {description}" for name, description in SLASH_COMMANDS]
    return "Slash commands:\n" + "\n".join(rows)


def agent_status(agent: Agent) -> str:
    """Return a compact status block for slash commands."""

    if agent.no_tools:
        tools = "disabled"
    elif agent.enabled_tools is None:
        tools = "all"
    else:
        tools = ", ".join(sorted(agent.enabled_tools)) or "none"
    return "\n".join(
        [
            f"model: {agent.client.model}",
            f"cwd: {agent.cwd}",
            f"max_steps: {agent.max_steps}",
            f"temperature: {agent.temperature}",
            f"tools: {tools}",
        ]
    )


def agent_tools(agent: Agent) -> str:
    """Return enabled tool names for slash commands."""

    if agent.no_tools:
        return "Tools are disabled."
    if agent.enabled_tools is None:
        names = agent.registry.names()
    else:
        names = sorted(agent.enabled_tools)
    return "Enabled tools: " + (", ".join(names) if names else "none")


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
        if stripped == "/commands":
            print(slash_command_help(), file=out)
            continue
        if stripped == "/clear":
            if getattr(out, "isatty", lambda: False)():
                print("\033[H\033[J", end="", file=out)
            print("system> Transcript cleared.", file=out)
            continue
        if stripped == "/reset":
            messages = agent.initial_messages()
            print("system> Conversation memory reset.", file=out)
            continue
        if stripped == "/status":
            print(f"system> {agent_status(agent)}", file=out)
            continue
        if stripped == "/tools":
            print(f"system> {agent_tools(agent)}", file=out)
            continue
        if stripped.startswith("/"):
            print("error> Unknown slash command. Type /commands.", file=out)
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
        input_line = InputLine()
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
            line, cursor_col = input_view(input_line.text, input_line.cursor, width)
            try:
                stdscr.addstr(transcript_height, 0, status_line[: max(0, width - 1)], curses.A_REVERSE)
                stdscr.addstr(transcript_height + 1, 0, line[: max(0, width - 1)])
                stdscr.move(transcript_height + 1, cursor_col)
            except curses.error:
                pass
            stdscr.refresh()

        def submit() -> None:
            nonlocal messages, scroll, status
            prompt = input_line.text.strip()
            input_line.clear()
            if not prompt:
                return
            if prompt in {"/quit", "/exit", ":q"}:
                raise KeyboardInterrupt
            if prompt == "/help":
                add("system", HELP_TEXT)
                status = "help"
                scroll = 10**9
                return
            if prompt == "/commands":
                add("system", slash_command_help())
                status = "commands"
                scroll = 10**9
                return
            if prompt == "/clear":
                entries.clear()
                add("system", "Transcript cleared.")
                status = "cleared"
                scroll = 0
                return
            if prompt == "/reset":
                messages = agent.initial_messages()
                add("system", "Conversation memory reset.")
                status = "reset"
                scroll = 10**9
                return
            if prompt == "/status":
                add("system", agent_status(agent))
                status = "status"
                scroll = 10**9
                return
            if prompt == "/tools":
                add("system", agent_tools(agent))
                status = "tools"
                scroll = 10**9
                return
            if prompt.startswith("/"):
                add("error", "Unknown slash command. Type /commands.")
                status = "error"
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
                input_line.backspace()
                continue
            if key == curses.KEY_DC:
                input_line.delete()
                continue
            if key == curses.KEY_LEFT:
                input_line.move_left()
                continue
            if key == curses.KEY_RIGHT:
                input_line.move_right()
                continue
            if key == curses.KEY_HOME or key == 1:
                input_line.move_start()
                continue
            if key == curses.KEY_END or key == 5:
                input_line.move_end()
                continue
            if key == 23:
                input_line.kill_previous_word()
                continue
            if key == 12:
                stdscr.clear()
                status = "redrawn"
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
                    input_line.insert(char)

    try:
        return int(curses.wrapper(_main))
    except (KeyboardInterrupt, EOFError):
        return 0


def run_tui(agent: Agent, *, runner: Callable[[Agent], int] | None = None) -> int:
    """Run the best available interactive UI."""

    selected_runner = runner or run_curses_tui
    return selected_runner(agent)
