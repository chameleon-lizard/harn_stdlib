# harn module documentation

`harn` is a dependency-free Python package that runs a compact coding agent
against OpenRouter's OpenAI-compatible chat-completions API.

## Modules

- `config.py` contains defaults such as `deepseek-v4-flash`,
  `OPENROUTER_API_KEY`, timeout, max steps, and tool names.
- `settings.py` loads optional JSON user config from `$HOME/.harn/harn.json`
  or `--config`.
- `client.py` implements the OpenRouter HTTP client with `urllib.request`,
  including SSE streaming for chat completions.
- `tools.py` exposes filesystem and shell tools: `read`, `write`, `edit`,
  `bash`, `grep`, `find`, and `ls`.
- `prompts.py` builds the system prompt and auto-loads the nearest
  `AGENTS.md`.
- `agent.py` runs the model/tool loop until the assistant returns a final
  answer.
- `sessions.py` persists TUI state and append-only logs under
  `$HOME/.harn/sessions`.
- `cli.py` provides the `python -m harn` command-line interface.
- `tui.py` provides the stdlib interactive terminal UI and fallback REPL.

## Dependency policy

Runtime code imports only Python standard-library modules. The package is
designed to run from source with:

```bash
python -m harn -p "List this repository"
```

The matching stdlib alias runs the same CLI:

```bash
python -m harn_stdlib -p "List this repository"
```

Run without a prompt to open the TUI:

```bash
python -m harn
```

The TUI supports slash commands (`/help`, `/commands`, `/clear`, `/resume`,
`/reset`, `/status`, `/trace`, `/tools`, `/quit`) and shell-like input editing with
Left/Right, Ctrl+A, Ctrl+E, Ctrl+W, Ctrl+L, and Ctrl+O. Ctrl+O toggles full
display for collapsed trace entries.

The TUI path streams OpenRouter chunks as they arrive. The agent loop emits
trace events for OpenRouter reasoning fields, tool calls, bash command
feedback, and edit diffs. TUI trace entries are collapsed to five lines by
default. Reasoning blocks use a high-contrast blue background, successful tool
traces use high-contrast green, and tool errors use high-contrast red. Bash
results with non-zero `exit_code` are classified as tool errors. OpenRouter
reasoning is preserved on assistant messages as `reasoning`,
`reasoning_content`, or `reasoning_details` when those fields are present in the
API response.

Each full-screen TUI run creates a session directory in
`$HOME/.harn/sessions/<session-id>/`. The directory contains `metadata.json`,
`state.json`, `events.jsonl`, and `transcript.log`. `/resume` loads the latest
previous session, `/resume <session-id>` loads a specific session, and `/clear`
only clears the visible transcript.

`/status` reports approximate context usage with a dependency-free chars/4 token
estimate, message count, transcript size, and session file sizes.

The curses TUI uses wide-character input, so UTF-8 text such as Cyrillic is
stored as Unicode instead of byte fragments. It also switches curses input to
raw mode so Ctrl+O reaches the TUI on terminals that otherwise treat it as
discard-output. Streamed trace entries are scoped to the active user turn and
reasoning chunks are overlap-deduplicated, so a second streamed response cannot
append above its question or fragment expanded trace output into repeated
chunks.

Runtime settings are resolved from CLI flags, then environment variables, then
`$HOME/.harn/harn.json`, then defaults. Config keys include `api_key`,
`openrouter_api_key`, `api_key_env`, `model`, `base_url`,
`openrouter_base_url`, `timeout`, `temperature`, `max_steps`, `max_tokens`,
`reasoning`, `reasoning_effort`, `reasoning_max_tokens`, `reasoning_enabled`,
and `reasoning_exclude`.

The CLI accepts common original-Harn flags such as `--print`, `--provider`,
`--thinking`, `--tools/-t`, `--no-tools/-nt`, `--list-models`, `--offline`,
`--tui`, and `--no-context-files/-nc`. Unsupported stateful subsystems are parsed for
compatibility but are not implemented in this dependency-free runtime.

The agent loop treats an empty assistant response without tool calls as an
incomplete turn. It appends a short continuation prompt and retries until the
model either calls a tool, returns a non-empty final answer, or reaches
`max_steps`.
