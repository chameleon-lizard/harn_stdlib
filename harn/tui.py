"""Stdlib interactive terminal UI for Harn."""

from __future__ import annotations

import json
import locale
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .agent import Agent, AgentError, AgentTraceEvent, append_stream_chunk
from .client import OpenRouterError
from .sessions import SessionError, SessionStore


@dataclass
class TranscriptEntry:
    role: str
    content: str
    collapsible: bool = False
    event_id: str | None = None


@dataclass
class DisplayLine:
    text: str
    role: str


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
    ("/continue", "list sessions or resume a numbered session"),
    ("/resume", "resume the latest or named session"),
    ("/reset", "reset conversation memory"),
    ("/status", "show model, cwd, and loop settings"),
    ("/trace", "toggle expanded trace details"),
    ("/tools", "show enabled local tools"),
    ("/quit", "exit the TUI"),
)


HELP_TEXT = """Slash commands:
/help      show this help
/commands  list slash commands
/clear     clear the visible transcript
/continue  list sessions or resume a numbered session
/resume    resume the latest or named session
/reset     reset conversation memory
/status    show model, cwd, and loop settings
/trace     toggle expanded trace details
/tools     show enabled local tools
/quit      exit the TUI

Keys:
Enter submits a message.
Left/Right move the cursor.
Ctrl+A/Ctrl+E move to start/end.
Ctrl+W deletes the previous word.
Ctrl+L redraws the screen.
Ctrl+O expands/collapses reasoning, diffs, and tool results.
Up/Down/PageUp/PageDown scroll the transcript.

Trace colors:
Reasoning blocks use a high-contrast blue background.
Tool calls, successful results, and diffs use a high-contrast green background.
Tool errors use a high-contrast red background.
"""


def collapse_content(content: str, *, expanded: bool = False, preview_lines: int = 5) -> str:
    """Return full content or a five-line preview for collapsible trace blocks."""

    if expanded:
        return content
    lines = content.splitlines()
    if len(lines) <= preview_lines:
        return content
    hidden = len(lines) - preview_lines
    preview = lines[:preview_lines]
    preview.append(f"... ({hidden} more line(s); Ctrl+O to expand)")
    return "\n".join(preview)


def render_transcript_lines(
    entries: list[TranscriptEntry],
    width: int,
    *,
    expand_collapsible: bool = False,
    preview_lines: int = 5,
) -> list[DisplayLine]:
    """Render transcript entries into display-width text lines with roles."""

    safe_width = max(20, width)
    lines: list[DisplayLine] = []
    for entry in entries:
        prefix = f"{entry.role}> "
        visible_content = collapse_content(
            entry.content,
            expanded=expand_collapsible or not entry.collapsible,
            preview_lines=preview_lines,
        )
        content = visible_content.rstrip() or "(empty)"
        paragraphs = content.splitlines() or [""]
        first = True
        for paragraph in paragraphs:
            available = max(10, safe_width - (len(prefix) if first else 2))
            wrapped = textwrap.wrap(paragraph, width=available, replace_whitespace=False) or [""]
            for item in wrapped:
                if first:
                    lines.append(DisplayLine((prefix + item)[:safe_width], entry.role))
                    first = False
                else:
                    lines.append(DisplayLine(("  " + item)[:safe_width], entry.role))
        lines.append(DisplayLine("", entry.role))
    return lines


def wrap_transcript(
    entries: list[TranscriptEntry],
    width: int,
    *,
    expand_collapsible: bool = False,
    preview_lines: int = 5,
) -> list[str]:
    """Render transcript entries into display-width text lines."""

    lines = render_transcript_lines(
        entries,
        width,
        expand_collapsible=expand_collapsible,
        preview_lines=preview_lines,
    )
    return [line.text for line in lines]


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
            f"reasoning: {agent.reasoning or 'auto'}",
            f"tools: {tools}",
        ]
    )


def context_chars(messages: list[dict[str, object]]) -> int:
    """Return a rough serialized context size in characters."""

    total = 0
    for message in messages:
        try:
            total += len(json.dumps(message, ensure_ascii=False, separators=(",", ":")))
        except (TypeError, ValueError):
            total += len(str(message))
    return total


def approx_tokens(chars: int) -> int:
    """Estimate token count using a dependency-free chars/4 heuristic."""

    if chars <= 0:
        return 0
    return max(1, (chars + 3) // 4)


def path_size(path: object) -> int:
    """Return file size or zero when the file is unavailable."""

    try:
        return int(path.stat().st_size)  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        return 0


def session_status(
    session_store: SessionStore | None,
    messages: list[dict[str, object]],
    entries: list[TranscriptEntry],
) -> str:
    """Return session and approximate context usage stats."""

    chars = context_chars(messages)
    transcript_chars = sum(len(entry.content) for entry in entries)
    lines = [
        f"session: {session_store.session_id if session_store else 'disabled'}",
        f"context_messages: {len(messages)}",
        f"context_estimate: ~{approx_tokens(chars)} tokens ({chars} chars, chars/4)",
        f"transcript_entries: {len(entries)}",
        f"transcript_chars: {transcript_chars}",
    ]
    if session_store:
        lines.extend(
            [
                f"session_path: {session_store.path}",
                f"state_bytes: {path_size(session_store.state_path())}",
                f"events_bytes: {path_size(session_store.events_path())}",
                f"transcript_log_bytes: {path_size(session_store.transcript_path())}",
            ]
        )
    return "\n".join(lines)


def safe_session_metadata(store: SessionStore) -> dict[str, object]:
    """Return session metadata, ignoring corrupt session folders in listings."""

    try:
        return store.metadata()
    except SessionError:
        return {}


def recent_sessions(
    *,
    root: Path | None = None,
    exclude: str | None = None,
    limit: int = 20,
) -> list[SessionStore]:
    """Return recent sessions sorted newest first."""

    sessions = []
    for store in SessionStore.list(root=root):
        if exclude and store.session_id == exclude:
            continue
        sessions.append(store)
    sessions.sort(key=lambda store: str(safe_session_metadata(store).get("updated_at") or ""), reverse=True)
    return sessions[:limit]


def format_session_choices(sessions: list[SessionStore]) -> str:
    """Return a numbered session picker for /continue."""

    if not sessions:
        return "No previous sessions found."
    rows = ["Recent sessions:"]
    for index, store in enumerate(sessions, start=1):
        metadata = safe_session_metadata(store)
        updated = str(metadata.get("updated_at") or "unknown")
        model = str(metadata.get("model") or "unknown-model")
        cwd = str(metadata.get("cwd") or "")
        cwd_part = f" cwd={cwd}" if cwd else ""
        rows.append(f"{index}. {store.session_id} updated={updated} model={model}{cwd_part}")
    rows.append("Use /continue <number> or /continue <session-id>.")
    return "\n".join(rows)


def select_continue_session(
    target: str,
    choices: list[SessionStore],
    *,
    current_session_id: str | None = None,
) -> SessionStore:
    """Resolve a /continue target from a numbered list or session id."""

    stripped = target.strip()
    if stripped.isdigit():
        if not choices:
            choices = recent_sessions(exclude=current_session_id)
        index = int(stripped)
        if 1 <= index <= len(choices):
            return choices[index - 1]
        raise SessionError(f"No session numbered {index}. Run /continue to list available sessions.")
    return SessionStore.open(stripped)


def agent_tools(agent: Agent) -> str:
    """Return enabled tool names for slash commands."""

    if agent.no_tools:
        return "Tools are disabled."
    if agent.enabled_tools is None:
        names = agent.registry.names()
    else:
        names = sorted(agent.enabled_tools)
    return "Enabled tools: " + (", ".join(names) if names else "none")


def format_trace_event(event: AgentTraceEvent, *, expanded: bool = False) -> str:
    """Format one trace event for transcript output."""

    content = trace_event_content(event)
    return collapse_content(content, expanded=expanded or not event.collapsible)


def trace_event_content(event: AgentTraceEvent) -> str:
    """Return the transcript content for a trace event."""

    if event.kind == "assistant":
        return event.content
    return f"{event.title}\n{event.content}" if event.content else event.title


def trace_event_id(event: AgentTraceEvent, event_prefix: str = "") -> str | None:
    """Return a transcript-scoped event id for a trace event."""

    if not event.event_id:
        return None
    return f"{event_prefix}:{event.event_id}" if event_prefix else event.event_id


def upsert_trace_entry(entries: list[TranscriptEntry], event: AgentTraceEvent, event_prefix: str = "") -> None:
    """Append a trace event or extend its existing transcript entry."""

    event_id = trace_event_id(event, event_prefix)
    if event_id:
        for entry in reversed(entries):
            if entry.event_id == event_id:
                if event.append and event.kind == "reasoning":
                    entry.content = append_stream_text(entry.content, event.content)
                elif event.append:
                    entry.content += event.content
                else:
                    entry.content = trace_event_content(event)
                entry.role = event.kind
                entry.collapsible = event.collapsible
                return
    entries.append(
        TranscriptEntry(
            event.kind,
            trace_event_content(event),
            collapsible=event.collapsible,
            event_id=event_id,
        )
    )


def append_stream_text(existing: str, chunk: str) -> str:
    """Append streamed display text while removing repeated overlap."""

    if existing.startswith("reasoning:") and "\n" in existing:
        heading, body = existing.split("\n", 1)
        return heading + "\n" + append_stream_chunk(body, chunk)
    return append_stream_chunk(existing, chunk)


def setup_colors(curses_module: object) -> dict[str, int]:
    """Initialize curses color pairs for trace roles."""

    pairs: dict[str, int] = {}
    try:
        curses_module.start_color()
        curses_module.use_default_colors()
        curses_module.init_pair(1, curses_module.COLOR_WHITE, curses_module.COLOR_BLUE)
        curses_module.init_pair(2, curses_module.COLOR_BLACK, curses_module.COLOR_GREEN)
        curses_module.init_pair(3, curses_module.COLOR_WHITE, curses_module.COLOR_RED)
        pairs = {"reasoning": 1, "tool": 2, "result": 2, "diff": 2, "error": 3}
    except Exception:
        return {}
    return pairs


def attr_for_role(curses_module: object, color_pairs: dict[str, int], role: str) -> int:
    """Return a curses attribute for a transcript role."""

    pair = color_pairs.get(role)
    if not pair:
        return 0
    try:
        return curses_module.color_pair(pair) | curses_module.A_BOLD
    except Exception:
        return 0


def configure_curses_input(curses_module: object, stdscr: object) -> None:
    """Configure curses input so control keys reach the TUI."""

    curses_module.curs_set(1)
    try:
        curses_module.raw()
    except Exception:
        try:
            curses_module.cbreak()
        except Exception:
            pass
    stdscr.keypad(True)


def key_code(key: object) -> int | None:
    """Return an integer key code for curses string/int keys."""

    if isinstance(key, str) and len(key) == 1:
        return ord(key)
    if isinstance(key, int):
        return key
    return None


def is_control_key(key: object, code: int) -> bool:
    """Return whether a curses key is the requested control character."""

    return key_code(key) == code


def serialize_entries(entries: list[TranscriptEntry]) -> list[dict[str, object]]:
    """Serialize transcript entries for session state."""

    return [
        {
            "role": entry.role,
            "content": entry.content,
            "collapsible": entry.collapsible,
            "event_id": entry.event_id,
        }
        for entry in entries
    ]


def deserialize_entries(raw_entries: object) -> list[TranscriptEntry]:
    """Load transcript entries from session state."""

    if not isinstance(raw_entries, list):
        return []
    entries: list[TranscriptEntry] = []
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            continue
        entries.append(
            TranscriptEntry(
                role=str(raw_entry.get("role") or "system"),
                content=str(raw_entry.get("content") or ""),
                collapsible=bool(raw_entry.get("collapsible") or False),
                event_id=str(raw_entry["event_id"]) if raw_entry.get("event_id") is not None else None,
            )
        )
    return entries


def deserialize_messages(raw_messages: object, fallback: list[dict[str, object]]) -> list[dict[str, object]]:
    """Load messages from session state."""

    if not isinstance(raw_messages, list):
        return fallback
    messages = [item for item in raw_messages if isinstance(item, dict)]
    return messages or fallback


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
        if stripped.startswith("/continue"):
            print("system> /continue is available in the full-screen TUI.", file=out)
            continue
        if stripped.startswith("/resume"):
            print("system> /resume is available in the full-screen TUI.", file=out)
            continue
        if stripped == "/reset":
            messages = agent.initial_messages()
            print("system> Conversation memory reset.", file=out)
            continue
        if stripped == "/status":
            print(f"system> {agent_status(agent)}\n{session_status(None, messages, [])}", file=out)
            continue
        if stripped == "/trace":
            print("system> Full-screen TUI toggles trace expansion with Ctrl+O.", file=out)
            continue
        if stripped == "/tools":
            print(f"system> {agent_tools(agent)}", file=out)
            continue
        if stripped.startswith("/"):
            print("error> Unknown slash command. Type /commands.", file=out)
            continue
        try:
            def print_trace(event: AgentTraceEvent) -> None:
                print(f"{event.kind}> {format_trace_event(event)}", file=out)

            result = agent.run_turn(messages, prompt, trace_callback=print_trace)
        except (AgentError, OpenRouterError) as exc:
            print(f"error> {exc}", file=out)
            continue
        messages = result.messages
        print(f"assistant> {result.content}", file=out)


def run_curses_tui(agent: Agent) -> int:
    """Run the full-screen curses TUI."""

    try:
        locale.setlocale(locale.LC_ALL, "")
    except locale.Error:
        pass

    try:
        import curses
    except ImportError:
        return run_line_repl(agent)

    def _main(stdscr: object) -> int:
        configure_curses_input(curses, stdscr)
        color_pairs = setup_colors(curses)

        entries = [
            TranscriptEntry("system", "Harn stdlib TUI. Type /help for commands, /quit to exit."),
        ]
        messages = agent.initial_messages()
        session_store: SessionStore | None = None
        try:
            session_store = SessionStore.create(metadata={"model": agent.client.model, "cwd": str(agent.cwd)})
        except (OSError, SessionError) as exc:
            entries.append(TranscriptEntry("error", f"Session logging disabled: {exc}"))
        input_line = InputLine()
        scroll = 0
        status = "ready"
        expanded_traces = False
        turn_counter = 0
        continue_choices: list[SessionStore] = []

        def persist_state() -> None:
            if not session_store:
                return
            try:
                session_store.save_state(messages, serialize_entries(entries))
            except (OSError, SessionError):
                pass

        def record_event(role: str, content: str, **metadata: object) -> None:
            if not session_store:
                return
            try:
                session_store.append_event(role, content, metadata)
            except (OSError, SessionError):
                pass

        record_event("system", entries[0].content)
        persist_state()

        def add(
            role: str,
            content: str,
            *,
            collapsible: bool = False,
            event_id: str | None = None,
            append: bool = False,
        ) -> None:
            if event_id:
                for entry in reversed(entries):
                    if entry.event_id == event_id:
                        entry.content = entry.content + content if append else content
                        entry.role = role
                        entry.collapsible = collapsible
                        record_event(role, content, event_id=event_id, append=append, collapsible=collapsible)
                        persist_state()
                        return
            entries.append(TranscriptEntry(role, content, collapsible=collapsible, event_id=event_id))
            record_event(role, content, event_id=event_id, append=append, collapsible=collapsible)
            persist_state()

        def add_trace(event: AgentTraceEvent, event_prefix: str = "") -> None:
            upsert_trace_entry(entries, event, event_prefix)
            record_event(
                event.kind,
                event.content,
                title=event.title,
                event_id=trace_event_id(event, event_prefix),
                append=event.append,
                collapsible=event.collapsible,
            )

        def resume_loaded_session(loaded: SessionStore) -> None:
            nonlocal entries, messages, session_store, status
            state = loaded.load_state()
            loaded_entries = deserialize_entries(state.get("entries"))
            entries = loaded_entries or [TranscriptEntry("system", f"Resumed empty session {loaded.session_id}.")]
            messages = deserialize_messages(state.get("messages"), agent.initial_messages())
            session_store = loaded
            add("system", f"Resumed session {loaded.session_id}.")
            status = f"resumed {loaded.session_id}"

        def render() -> None:
            nonlocal scroll
            stdscr.erase()
            height, width = stdscr.getmaxyx()
            transcript_height = max(1, height - 3)
            lines = render_transcript_lines(entries, width, expand_collapsible=expanded_traces)
            max_scroll = max(0, len(lines) - transcript_height)
            scroll = max(0, min(scroll, max_scroll))
            visible = lines[scroll : scroll + transcript_height]

            for y, line in enumerate(visible):
                try:
                    attr = attr_for_role(curses, color_pairs, line.role)
                    text = line.text[: max(0, width - 1)]
                    if attr and text:
                        text = text.ljust(max(0, width - 1))
                    stdscr.addstr(y, 0, text, attr)
                except curses.error:
                    pass

            detail_state = "trace full" if expanded_traces else "trace short"
            status_line = f" {status} | {detail_state} | {len(entries)} entries | scroll {scroll}/{max_scroll} "
            line, cursor_col = input_view(input_line.text, input_line.cursor, width)
            try:
                stdscr.addstr(transcript_height, 0, status_line[: max(0, width - 1)], curses.A_REVERSE)
                stdscr.addstr(transcript_height + 1, 0, line[: max(0, width - 1)])
                stdscr.move(transcript_height + 1, cursor_col)
            except curses.error:
                pass
            stdscr.refresh()

        def submit() -> None:
            nonlocal continue_choices, entries, messages, scroll, session_store, status, expanded_traces, turn_counter
            prompt = input_line.text.strip()
            input_line.clear()
            if not prompt:
                return
            command, _space, command_arg = prompt.partition(" ")
            if command in {"/quit", "/exit", ":q"}:
                raise KeyboardInterrupt
            if command == "/help":
                add("system", HELP_TEXT)
                status = "help"
                scroll = 10**9
                return
            if command == "/commands":
                add("system", slash_command_help())
                status = "commands"
                scroll = 10**9
                return
            if command == "/clear":
                entries.clear()
                add("system", "Transcript cleared.")
                status = "cleared"
                scroll = 0
                return
            if command == "/continue":
                target = command_arg.strip()
                try:
                    if not target:
                        continue_choices = recent_sessions(
                            exclude=session_store.session_id if session_store else None
                        )
                        add("system", format_session_choices(continue_choices))
                        status = "continue"
                        scroll = 10**9
                        return
                    loaded = select_continue_session(
                        target,
                        continue_choices,
                        current_session_id=session_store.session_id if session_store else None,
                    )
                    resume_loaded_session(loaded)
                    scroll = 10**9
                except (OSError, SessionError) as exc:
                    add("error", str(exc))
                    status = "error"
                    scroll = 10**9
                return
            if command == "/resume":
                target = command_arg.strip()
                try:
                    loaded = SessionStore.open(target) if target else SessionStore.latest(
                        exclude=session_store.session_id if session_store else None
                    )
                    if loaded is None:
                        add("error", "No previous session found.")
                        status = "error"
                        scroll = 10**9
                        return
                    resume_loaded_session(loaded)
                    scroll = 10**9
                except (OSError, SessionError) as exc:
                    add("error", str(exc))
                    status = "error"
                    scroll = 10**9
                return
            if command == "/reset":
                messages = agent.initial_messages()
                add("system", "Conversation memory reset.")
                status = "reset"
                scroll = 10**9
                return
            if command == "/status":
                add("system", agent_status(agent) + "\n" + session_status(session_store, messages, entries))
                status = "status"
                scroll = 10**9
                return
            if command == "/trace":
                expanded_traces = not expanded_traces
                status = "trace full" if expanded_traces else "trace short"
                add("system", f"Trace details are now {'expanded' if expanded_traces else 'collapsed'}.")
                scroll = 10**9
                return
            if command == "/tools":
                add("system", agent_tools(agent))
                status = "tools"
                scroll = 10**9
                return
            if command.startswith("/"):
                add("error", "Unknown slash command. Type /commands.")
                status = "error"
                scroll = 10**9
                return

            add("user", prompt)
            status = "working..."
            scroll = 10**9
            render()
            try:
                turn_counter += 1
                event_prefix = f"turn:{turn_counter}"

                def on_trace(event: AgentTraceEvent) -> None:
                    nonlocal scroll
                    add_trace(event, event_prefix)
                    scroll = 10**9
                    render()

                result = agent.run_turn(messages, prompt, trace_callback=on_trace, stream=True)
            except (AgentError, OpenRouterError) as exc:
                add("error", str(exc))
                status = "error"
                return
            messages = result.messages
            if result.content and not any(event.kind == "assistant" for event in result.trace):
                add("assistant", result.content)
            persist_state()
            status = f"done: {result.steps} step(s), {result.tool_calls} tool call(s)"
            scroll = 10**9

        while True:
            render()
            try:
                key = stdscr.get_wch()
            except curses.error:
                continue
            if isinstance(key, str):
                if is_control_key(key, 3) or is_control_key(key, 4):
                    return 0
                if key in ("\n", "\r"):
                    try:
                        submit()
                    except KeyboardInterrupt:
                        return 0
                    continue
                if key in ("\b", "\x7f"):
                    input_line.backspace()
                    continue
                if is_control_key(key, 1):
                    input_line.move_start()
                    continue
                if is_control_key(key, 5):
                    input_line.move_end()
                    continue
                if is_control_key(key, 23):
                    input_line.kill_previous_word()
                    continue
                if is_control_key(key, 12):
                    stdscr.clear()
                    status = "redrawn"
                    continue
                if is_control_key(key, 15):
                    expanded_traces = not expanded_traces
                    status = "trace full" if expanded_traces else "trace short"
                    continue
                if key.isprintable():
                    input_line.insert(key)
                continue

            if is_control_key(key, 3) or is_control_key(key, 4):
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
            if key == curses.KEY_HOME or is_control_key(key, 1):
                input_line.move_start()
                continue
            if key == curses.KEY_END or is_control_key(key, 5):
                input_line.move_end()
                continue
            if is_control_key(key, 23):
                input_line.kill_previous_word()
                continue
            if is_control_key(key, 12):
                stdscr.clear()
                status = "redrawn"
                continue
            if is_control_key(key, 15):
                expanded_traces = not expanded_traces
                status = "trace full" if expanded_traces else "trace short"
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
