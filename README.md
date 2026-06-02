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
- An OpenRouter API key in `OPENROUTER_API_KEY`

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
`--mode text|json`, `--offline`, and `--no-context-files/-nc`. Session, TUI,
extension, theme, skill, and export flags are parsed for compatibility, but the
stdlib runtime does not implement those subsystems.

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
setup.cfg             legacy editable-install metadata for both scripts
WIKI.md               project feature summary
PROGRESS.md           implemented and planned work
OPS.md                operations runbook
```
