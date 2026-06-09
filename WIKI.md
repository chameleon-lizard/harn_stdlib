# Harn stdlib rewrite wiki

## Executive summary

This repository is a stdlib-only rewrite of `secemp9/harn`. The original
multi-package workspace depended on `httpx`, `pydantic`, `click`, `rich`,
provider SDKs, TUI libraries, and pytest. The current implementation keeps the
core useful surface as a compact terminal coding agent:

- one Python package, `harn`;
- one compatibility package, `harn_stdlib`, that re-exports `harn`;
- no runtime dependencies in `pyproject.toml`;
- direct source execution with `python -m harn`;
- matched alias execution with `python -m harn_stdlib`;
- matched console entry points `harn` and `harn-stdlib`;
- legacy setuptools metadata in `setup.cfg` so both scripts are created by
  pip/setuptools environments;
- OpenRouter chat-completions calls through `urllib.request`;
- default model `deepseek-v4-flash`;
- API key loaded from CLI flags, environment, or `$HOME/.harn/harn.json`;
- filesystem and shell tools exposed through OpenAI-compatible tool calling;
- dependency-free interactive TUI through stdlib `curses`, with line-mode
  fallback, streaming output, editable input, slash commands, and collapsed
  trace output;
- local project instructions loaded from nearest `AGENTS.md`;
- separate prompt eval directory using `AGENTS.md` and `DesignDoc.md`.

## Runtime behavior

The CLI builds a prompt from positional text, stdin, `@file` attachments, and
`--prompt-file` attachments. It creates an `OpenRouterClient`, builds a system
prompt, and runs an agent loop.

When run in an interactive terminal without a prompt, the CLI opens the stdlib
TUI. The same UI can be forced with `--tui` or disabled with `--no-tui`. The TUI
keeps a single chat transcript for the session and supports `/help`,
`/commands`, `/clear`, `/continue`, `/resume`, `/reset`, `/status`, `/trace`,
`/skill`, `/skills`, `/tools`, and `/quit`. The input line supports Left/Right
cursor movement, Ctrl+A/Ctrl+E for start/end, Ctrl+W for previous-word deletion,
Ctrl+L for screen redraw, and Ctrl+O for expanding or collapsing trace details.
Esc or Ctrl+C cancels an in-flight generation. The TUI shows OpenRouter
reasoning fields when returned, plus tool calls, bash command results, and edit diffs.
Trace entries collapse to five lines by default. Reasoning blocks use a
high-contrast blue background, successful tool traces use high-contrast green,
and tool errors use high-contrast red. Bash results with non-zero `exit_code`
are treated as errors. The curses input path reads wide characters and raw
control keys so UTF-8 prompts such as Cyrillic are kept as Unicode and Ctrl+O is
not swallowed by terminal discard-output handling. Streamed trace ids are scoped
per user turn so later responses append below the latest question, not into an
earlier assistant block. Single-newline reasoning fragments are normalized into
spaces, and newlines inside identifiers are removed, so expanded traces do not
show one provider chunk per line.

TUI sessions are stored in `$HOME/.harn/sessions`. Each session has its own
folder containing `metadata.json`, `state.json`, `events.jsonl`, and
`transcript.log`. `/resume` loads the latest previous session and `/resume
<session-id>` loads a specific session. `/continue` lists recent sessions and
`/continue <number>` or `/continue <session-id>` loads the chosen session.
`/clear` clears visible state but keeps the append-only logs. `/status`
includes approximate context usage, transcript size, and session file byte
counts.

Configuration is resolved in this order: CLI flags, environment variables,
`$HOME/.harn/harn.json`, then defaults. Supported config keys include
`api_key`, `openrouter_api_key`, `api_key_env`, `model`, `base_url`,
`openrouter_base_url`, `timeout`, `temperature`, `max_steps`, and
`max_tokens`, `reasoning`, `reasoning_effort`, `reasoning_max_tokens`,
`reasoning_enabled`, `reasoning_exclude`, `skills`, and `skills_dir`.

Skills are local instruction packs stored under `$HOME/.harn/skills` by
default. Harn discovers `<name>/SKILL.md` directories and single `*.md` files.
Use `--list-skills` to list them, `--skill <name>` to enable one or more skills
from CLI, config key `skills` or `HARN_SKILLS` to enable default skills, and
`--skills-dir`, config key `skills_dir`, or `HARN_SKILLS_DIR` to use a
non-default directory. In the TUI, `/skills` lists available and active skills,
`/skill <name>[,<name>...]` enables skills, and `/skill off` clears active
skills. Active skill markdown is rendered into the system prompt for subsequent
turns.

The CLI also accepts original-Harn compatibility flags where a stdlib
OpenRouter runtime can support them. Examples include `--print`, `--provider`,
`--thinking`, `--tools/-t`, `--no-tools/-nt`, `--no-builtin-tools/-nbt`,
`--list-models`, `--mode text|json`, `--offline`, `--tui`, and
`--no-context-files/-nc`. State/session/resource flags are parsed so old
commands fail less abruptly, but those subsystems are intentionally not
implemented in the stdlib rewrite.

The agent loop sends messages to OpenRouter. The TUI path uses OpenRouter SSE
streaming so assistant text and reasoning chunks can be shown before the full
response completes. If the model returns tool calls, Harn executes them locally
and appends tool results to the conversation. The loop stops when the assistant
returns a final message or when `--max-steps` is reached. If the model returns
`reasoning`, `reasoning_content`, or `reasoning_details`, Harn preserves those
fields in the assistant message and emits trace events for the TUI.

## Modules

`harn/config.py` defines defaults such as version, model, timeout, API key env
var, and tool names.

`harn/settings.py` loads optional JSON user config from `$HOME/.harn/harn.json`
or an explicit `--config` path.

`harn/client.py` is a minimal OpenRouter client. It serializes JSON requests,
sends them to `/chat/completions`, decodes JSON responses, and raises
`OpenRouterError` on HTTP/API failures.

`harn/tools.py` contains the tool registry and local tool implementations.
Paths are scoped to `--cwd` unless `--allow-outside-cwd` is set.

`harn/prompts.py` builds the base system prompt and finds `AGENTS.md` by walking
upward from the configured cwd.

`harn/skills.py` discovers and loads `SKILL.md` files from `$HOME/.harn/skills`
or another configured skills directory.

`harn/agent.py` orchestrates the model/tool loop.

`harn/cli.py` provides argument parsing and terminal output.

`harn/tui.py` provides the stdlib curses TUI and line-mode fallback.

`harn/sessions.py` persists TUI state and append-only logs under
`$HOME/.harn/sessions`.

`setup.cfg` mirrors the console script metadata for package installers that
still consult setuptools configuration.

`harn_stdlib/` is a thin alias package. It contains no agent implementation and
imports from `harn`, so `harn` and `harn-stdlib` cannot drift in behavior.

## Test surface

`agent_eval_tests/test_static_stdlib.py` checks that the project declares no
runtime dependencies, imports no known external packages from the previous
implementation, that `harn` and `harn_stdlib` expose the same public API, and
that both module entry points print matching tools and version outputs. It also
checks that representative original-Harn flags parse in stdlib mode and covers
TUI dispatch/render helpers, editable input behavior, slash-command discovery,
config-file option resolution, SSE streaming parsing, session persistence,
numbered session selection for `/continue`, generation cancellation, skill
discovery and system-prompt injection, context/session status reporting,
reasoning preservation and overlap deduplication, streamed reasoning newline
normalization, tool result traces, non-zero bash error classification, and edit
diff traces.

`agent_eval_tests/test_prompt_eval.py` is a live eval suite. It is skipped by
default and runs only when `RUN_OPENROUTER_EVAL=1` and `OPENROUTER_API_KEY` are
set. It uses:

- `agent_eval_tests/prompts/AGENTS.md` to check instruction understanding;
- `agent_eval_tests/prompts/DesignDoc.md` to check design-doc understanding;
- a temporary directory to check real tool-based file creation.

## Removed features

The dependency-heavy original TUI, multi-provider SDK registry, OAuth flows,
image providers, rich rendering, and old pytest suite were removed. They were
not compatible with the requirement to use pure Python and stdlib only. A
smaller stdlib TUI now replaces the old TUI surface.

## Security notes

Secrets are read from environment variables or local user config. No API key is
stored in source, docs, tests, or git history for this branch. Tool access is
cwd-scoped by default.
