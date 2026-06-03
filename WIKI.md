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
- API key loaded from `OPENROUTER_API_KEY`;
- filesystem and shell tools exposed through OpenAI-compatible tool calling;
- dependency-free interactive TUI through stdlib `curses`, with line-mode
  fallback;
- local project instructions loaded from nearest `AGENTS.md`;
- separate prompt eval directory using `AGENTS.md` and `DesignDoc.md`.

## Runtime behavior

The CLI builds a prompt from positional text, stdin, `@file` attachments, and
`--prompt-file` attachments. It creates an `OpenRouterClient`, builds a system
prompt, and runs an agent loop.

When run in an interactive terminal without a prompt, the CLI opens the stdlib
TUI. The same UI can be forced with `--tui` or disabled with `--no-tui`. The TUI
keeps a single chat transcript for the session and supports `/help`, `/clear`,
and `/quit`.

The CLI also accepts original-Harn compatibility flags where a stdlib
OpenRouter runtime can support them. Examples include `--print`, `--provider`,
`--thinking`, `--tools/-t`, `--no-tools/-nt`, `--no-builtin-tools/-nbt`,
`--list-models`, `--mode text|json`, `--offline`, `--tui`, and
`--no-context-files/-nc`. State/session/resource flags are parsed so old
commands fail less abruptly, but those subsystems are intentionally not
implemented in the stdlib rewrite.

The agent loop sends messages to OpenRouter. If the model returns tool calls,
Harn executes them locally and appends tool results to the conversation. The
loop stops when the assistant returns a final message or when `--max-steps` is
reached.

## Modules

`harn/config.py` defines defaults such as version, model, timeout, API key env
var, and tool names.

`harn/client.py` is a minimal OpenRouter client. It serializes JSON requests,
sends them to `/chat/completions`, decodes JSON responses, and raises
`OpenRouterError` on HTTP/API failures.

`harn/tools.py` contains the tool registry and local tool implementations.
Paths are scoped to `--cwd` unless `--allow-outside-cwd` is set.

`harn/prompts.py` builds the base system prompt and finds `AGENTS.md` by walking
upward from the configured cwd.

`harn/agent.py` orchestrates the model/tool loop.

`harn/cli.py` provides argument parsing and terminal output.

`harn/tui.py` provides the stdlib curses TUI and line-mode fallback.

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
TUI dispatch/render helpers.

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

Secrets are read from environment variables. No API key is stored in source,
docs, tests, or git history for this branch. Tool access is cwd-scoped by
default.
