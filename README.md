# Harn

Harn is now a small, dependency-free terminal coding agent written with only
Python standard-library modules. It talks to OpenRouter through the
OpenAI-compatible chat-completions API and gives the model local tools for
reading, writing, editing, searching, listing, and running shell commands.

`harn` and `harn-stdlib` are matched entry points. The importable runtime is
`harn`; `harn_stdlib` is a compatibility alias that re-exports the same public
API and runs the same CLI.

## Requirements

- Python 3.9 or later
- An OpenRouter API key in `OPENROUTER_API_KEY` or `~/.harn/harn.json`

No package install is required when running from the repository.

Source install is also dependency-free at runtime and creates both console
commands:

```bash
python -m pip install --no-deps .
harn --version
harn-stdlib --version
```

## Quick start

```bash
export OPENROUTER_API_KEY="sk-or-v1-..."
python -m harn -p "List the important files in this repository"
```

Equivalent stdlib alias:

```bash
python -m harn_stdlib -p "List the important files in this repository"
```

Start the interactive stdlib TUI by running without a prompt, or force it with
`--tui`:

```bash
python -m harn
python -m harn --tui --cwd /path/to/project
```

Inside the TUI, type a prompt and press Enter. Commands: `/help`, `/clear`,
`/commands`, `/resume`, `/reset`, `/status`, `/trace`, `/tools`, and `/quit`.
The input line supports Left/Right, Ctrl+A, Ctrl+E, Ctrl+W, Ctrl+L, and Ctrl+O.
The transcript scrolls with Up/Down and PageUp/PageDown.

The TUI streams model output as OpenRouter chunks arrive. It shows reasoning
traces when OpenRouter returns `reasoning` or `reasoning_details`, plus tool
calls, bash command output, and edit diffs. These details are collapsed to five
lines by default; press Ctrl+O or run `/trace` to toggle full trace output.
Reasoning blocks use a high-contrast blue background, successful tool traces
use high-contrast green, and tool errors use high-contrast red. Bash results
with non-zero `exit_code` are treated as errors. UTF-8 input such as Cyrillic is
read through curses wide-character mode, and streamed trace blocks are scoped
per user turn so later replies stay below their question. Ctrl+O is read in
curses raw mode so terminal discard-output handling does not swallow it.

TUI sessions are saved under `~/.harn/sessions/<session-id>/` with
`metadata.json`, `state.json`, `events.jsonl`, and `transcript.log`. Use
`/resume` to resume the latest previous session or `/resume <session-id>` for a
specific session. `/clear` clears only the visible transcript; the append-only
logs remain on disk.

`/status` includes approximate session context usage: message count, serialized
context characters, a dependency-free chars/4 token estimate, transcript entry
counts, and session file sizes.

Optional user config is loaded from `~/.harn/harn.json` before defaults. CLI
flags win over environment variables, environment variables win over config,
and config wins over built-in defaults.

```json
{
  "api_key": "sk-or-v1-...",
  "model": "deepseek-v4-flash",
  "base_url": "https://openrouter.ai/api/v1",
  "timeout": 120,
  "temperature": 0.2,
  "max_steps": 8,
  "max_tokens": 4096,
  "reasoning": "enabled"
}
```

Use `--config /path/to/harn.json` for a different file or `--no-config` to
ignore the default config. `openrouter_api_key`, `openrouter_base_url`,
`api_key_env`, `reasoning_effort`, `reasoning_max_tokens`,
`reasoning_enabled`, and `reasoning_exclude` are also accepted config keys.

Reasoning can also be controlled with CLI flags:

```bash
python -m harn --reasoning enabled -p "Think visibly if the model supports it"
python -m harn --reasoning-max-tokens 2048 -p "Solve this carefully"
```

The default model is `deepseek-v4-flash`. Override it with `--model` or
`HARN_MODEL`:

```bash
python -m harn --model deepseek-v4-flash -p "Read README.md and summarize it"
```

Attach files with `@file` or `--prompt-file`:

```bash
python -m harn @README.md "What changed in this rewrite?"
python -m harn --prompt-file agent_eval_tests/prompts/DesignDoc.md -p "Name the invariants"
```

Run in a specific working directory:

```bash
python -m harn --cwd /path/to/project -p "Create a short TODO.md"
```

Disable tools for a pure model call:

```bash
python -m harn --no-tools -p "Answer without touching files"
```

Original Harn CLI compatibility flags are accepted where they make sense in a
stdlib/OpenRouter runtime, including `--print`, `--provider`, `--thinking`,
`--tools/-t`, `--no-tools/-nt`, `--no-builtin-tools/-nbt`, `--list-models`,
`--mode text|json`, `--offline`, `--tui`, and `--no-context-files/-nc`.
Session, extension, theme, skill, and export flags are parsed for
compatibility, but the stdlib runtime does not implement those subsystems.

## Tools

The agent exposes these tools to the model:

| Tool | Purpose |
|---|---|
| `read` | Read a UTF-8 text file |
| `write` | Create, overwrite, or append a UTF-8 text file |
| `edit` | Replace exact text in a UTF-8 text file |
| `bash` | Run a bash command in the configured cwd |
| `grep` | Search files with a Python regular expression |
| `find` | Find files by shell-style glob pattern |
| `ls` | List a directory |

By default, tool paths are restricted to the configured cwd. Use
`--allow-outside-cwd` only when the prompt explicitly needs access outside the
working directory.

## Tests

Static tests require only stdlib:

```bash
python -m unittest discover -s agent_eval_tests
```

The static suite verifies that `python -m harn` and `python -m harn_stdlib`
produce matching tool and version outputs, that the public APIs match, and
that original-Harn compatibility flags still parse.

Live OpenRouter evals use the copied `AGENTS.md` and `DesignDoc.md` prompts in
`agent_eval_tests/prompts/` and are opt-in:

```bash
RUN_OPENROUTER_EVAL=1 OPENROUTER_API_KEY="sk-or-v1-..." python -m unittest discover -s agent_eval_tests
```

The API key is intentionally read from the environment and is not committed.

## Project layout

```text
harn/                 stdlib runtime and CLI
harn_stdlib/          compatibility alias for harn / harn-stdlib
agent_eval_tests/     static and live prompt eval tests
setup.cfg             legacy setuptools metadata for both scripts
WIKI.md               project feature summary
PROGRESS.md           implemented and planned work
OPS.md                operations runbook
```
