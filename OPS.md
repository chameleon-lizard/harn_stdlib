# Harn operations runbook

## Purpose

This runbook lets an agent or operator deploy, configure, test, and diagnose
the stdlib-only Harn CLI.

## Build and deployment

No build step is required for source execution.

```bash
git clone https://github.com/secemp9/harn.git
cd harn
python -m harn --version
python -m harn_stdlib --version
```

Source install check:

```bash
python -m pip install --no-deps .
harn --version
harn-stdlib --version
```

Optional editable/package installation depends on the user's packaging tool,
but runtime operation from source does not need third-party packages.

## Configuration

Configuration can come from CLI flags, environment variables, or a JSON config
file. The precedence is CLI, environment, config, then defaults. The default
config path is `$HOME/.harn/harn.json`; use `--config` for another path or
`--no-config` to disable config loading.

Example config:

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

Accepted config keys include `api_key`, `openrouter_api_key`, `api_key_env`,
`model`, `base_url`, `openrouter_base_url`, `timeout`, `temperature`,
`max_steps`, `max_tokens`, `reasoning`, `reasoning_effort`,
`reasoning_max_tokens`, `reasoning_enabled`, and `reasoning_exclude`.

Required environment variables when no config key or CLI flag supplies the API
key:

| Variable | Description | Example |
|---|---|---|
| `OPENROUTER_API_KEY` | OpenRouter bearer token | `sk-or-v1-...` |

Optional environment variables:

| Variable | Description | Default |
|---|---|---|
| `HARN_MODEL` | Model passed to OpenRouter | `deepseek-v4-flash` |
| `OPENROUTER_BASE_URL` | API base URL | `https://openrouter.ai/api/v1` |
| `RUN_OPENROUTER_EVAL` | Enable live eval tests when set to `1` | unset |
| `HARN_EVAL_PROMPT_DIR` | Override live eval prompt directory | `agent_eval_tests/prompts` |

CLI options of operational interest:

```bash
python -m harn --help
python -m harn_stdlib --help
python -m harn --tui
python -m harn --config "$HOME/.harn/harn.json" -p "Inspect this project"
python -m harn --cwd /repo -p "Inspect this project"
python -m harn --no-tools -p "Answer without tools"
python -m harn --allow-outside-cwd -p "Read a specific external file"
python -m harn --reasoning enabled -p "Show reasoning traces when supported"
python -m harn --provider openai --model gpt-4o -p "Use OpenRouter provider prefixing"
```

## Health checks

Local import and CLI health:

```bash
python -m harn --version
python -m harn --list-tools
python -m harn_stdlib --version
python -m harn_stdlib --list-tools
python -m unittest discover -s agent_eval_tests
```

Live OpenRouter health:

```bash
RUN_OPENROUTER_EVAL=1 OPENROUTER_API_KEY="sk-or-v1-..." python -m unittest discover -s agent_eval_tests
```

Expected static result: twenty-five tests run, four live tests skipped when
`RUN_OPENROUTER_EVAL` is not set. The static suite includes parity checks for
`harn` and `harn_stdlib`, representative original-Harn CLI flag checks, and TUI
dispatch/render helper checks, plus config-file, TUI input-editing, SSE
streaming, session persistence, and trace event checks.

## Logs

Harn does not persist logs. CLI diagnostics are written to stderr. For
operational capture:

```bash
python -m harn -p "Prompt" >harn.stdout.log 2>harn.stderr.log
```

Filter common issues:

```bash
grep -i "openrouter" harn.stderr.log
grep -i "max_steps" harn.stderr.log
grep -i "tool_error" harn.stdout.log harn.stderr.log
```

## Common failure modes

Missing API key:

- Symptom: `harn: OPENROUTER_API_KEY is required`.
- Fix: export `OPENROUTER_API_KEY`, set `api_key` or `openrouter_api_key` in
  `$HOME/.harn/harn.json`, or pass `--api-key` for a one-off command.

OpenRouter rejects model:

- Symptom: `OpenRouter HTTP 400` or model-related API error.
- Fix: set `HARN_MODEL` or `--model` to a valid OpenRouter model.

Agent reaches max steps:

- Symptom: `Agent reached max_steps=N without a final answer`.
- Fix: increase `--max-steps`, simplify the prompt, or disable tools for pure
  summarization with `--no-tools`.

TUI does not open:

- Symptom: running `harn` without a prompt exits with an argparse prompt error.
- Fix: run from an interactive terminal, or force the UI with `harn --tui`.
  Use `--no-tui` in scripts where no prompt should be treated as an error.

TUI input editing does not behave like a shell:

- Expected keys: Left/Right move by character, Ctrl+A/Ctrl+E jump to
  start/end, Ctrl+W deletes the previous word, Ctrl+L redraws the screen, and
  Ctrl+O expands or collapses trace details.
- Slash commands: `/help`, `/commands`, `/clear`, `/continue`, `/resume`,
  `/reset`, `/status`, `/trace`, `/tools`, and `/quit`.
- UTF-8 text such as Cyrillic should appear normally. If it appears as mojibake,
  verify the terminal locale is UTF-8; the TUI reads wide characters through
  curses.

TUI answer appears above the latest question:

- Streamed assistant/reasoning blocks are keyed per user turn. If ordering
  regresses, check for duplicate `event_id` values across turns in TUI trace
  handling.

Reasoning or command feedback is missing in the TUI:

- Reasoning traces only appear when OpenRouter returns `reasoning` or
  `reasoning_details`; some models/providers do not expose them.
- Use `--reasoning enabled`, `--reasoning high`, or config key
  `"reasoning": "enabled"` to request reasoning from models that support it.
- Tool calls, bash command results, and edit diffs are shown as trace entries
  and collapse to five lines by default. Press Ctrl+O or run `/trace` to toggle
  full trace output.
- TUI streaming uses OpenRouter SSE chunks. Reasoning blocks use a
  high-contrast blue background, successful tool traces use high-contrast green,
  and tool errors use high-contrast red. Bash results with non-zero `exit_code`
  are classified as tool errors.
- Ctrl+O is read after switching curses input to raw mode. This avoids terminals
  swallowing Ctrl+O as discard-output.
- `/status` shows approximate context usage with message count, serialized
  context characters, a chars/4 token estimate, transcript size, and session log
  byte counts.
- Single-newline reasoning fragments are normalized into spaces. Newlines inside
  identifiers such as `exit_code` are removed so streamed reasoning remains
  readable after tool calls.

Session cannot be resumed:

- Sessions are stored in `$HOME/.harn/sessions/<session-id>/`.
- Each session folder contains `metadata.json`, `state.json`, `events.jsonl`,
  and `transcript.log`.
- Use `/resume` to load the latest previous session or `/resume <session-id>`
  to load a specific folder name.
- Use `/continue` to list recent sessions and `/continue <number>` to choose
  from that list. `/continue <session-id>` also loads a specific folder name.
- `/clear` changes visible transcript state but does not remove append-only log
  files.

Tool path rejected:

- Symptom: `TOOL_ERROR: Path is outside cwd`.
- Fix: run with the correct `--cwd` or use `--allow-outside-cwd` only when the
  prompt is trusted and requires it.

Shell command timeout:

- Symptom: tool output reports a bash timeout.
- Fix: increase the timeout in the prompt or ask the agent to run a smaller
  command.

## Backup and restore

The CLI does not create persistent state by default. Back up repository files
with git:

```bash
git status --short
git add -A
git commit -m "feat: Saved work"
```

Restore by checking out the desired git revision. Do not use destructive git
commands unless the operator explicitly requests them.

## Scaling

Harn is a single-process CLI. Scale by running independent processes with
separate working directories. There is no shared database or daemon to scale.

## Update and rollback

Update:

```bash
git pull --ff-only
python -m unittest discover -s agent_eval_tests
```

Rollback:

```bash
git log --oneline
git switch --detach <known-good-commit>
python -m harn --version
```
