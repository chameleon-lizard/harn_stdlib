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

Required environment variables:

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
python -m harn --cwd /repo -p "Inspect this project"
python -m harn --no-tools -p "Answer without tools"
python -m harn --allow-outside-cwd -p "Read a specific external file"
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

Expected static result: eleven tests run, four live tests skipped when
`RUN_OPENROUTER_EVAL` is not set. The static suite includes parity checks for
`harn` and `harn_stdlib`, plus representative original-Harn CLI flag checks.

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
- Fix: export `OPENROUTER_API_KEY` or pass `--api-key` for a one-off command.

OpenRouter rejects model:

- Symptom: `OpenRouter HTTP 400` or model-related API error.
- Fix: set `HARN_MODEL` or `--model` to a valid OpenRouter model.

Agent reaches max steps:

- Symptom: `Agent reached max_steps=N without a final answer`.
- Fix: increase `--max-steps`, simplify the prompt, or disable tools for pure
  summarization with `--no-tools`.

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
