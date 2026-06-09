# harn module documentation

`harn` is a dependency-free Python package that runs a compact coding agent
against OpenRouter's OpenAI-compatible chat-completions API.

## Modules

- `config.py` contains defaults such as `deepseek-v4-flash`,
  `OPENROUTER_API_KEY`, timeout, max steps, and tool names.
- `settings.py` loads optional JSON user config from `$HOME/.harn/harn.json`
  or `--config`.
- `client.py` implements the OpenRouter HTTP client with `urllib.request`.
- `tools.py` exposes filesystem and shell tools: `read`, `write`, `edit`,
  `bash`, `grep`, `find`, and `ls`.
- `prompts.py` builds the system prompt and auto-loads the nearest
  `AGENTS.md`.
- `agent.py` runs the model/tool loop until the assistant returns a final
  answer.
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

The TUI supports slash commands (`/help`, `/commands`, `/clear`, `/reset`,
`/status`, `/tools`, `/quit`) and shell-like input editing with Left/Right,
Ctrl+A, Ctrl+E, Ctrl+W, and Ctrl+L.

Runtime settings are resolved from CLI flags, then environment variables, then
`$HOME/.harn/harn.json`, then defaults. Config keys include `api_key`,
`openrouter_api_key`, `api_key_env`, `model`, `base_url`,
`openrouter_base_url`, `timeout`, `temperature`, `max_steps`, and
`max_tokens`.

The CLI accepts common original-Harn flags such as `--print`, `--provider`,
`--thinking`, `--tools/-t`, `--no-tools/-nt`, `--list-models`, `--offline`,
`--tui`, and `--no-context-files/-nc`. Unsupported stateful subsystems are parsed for
compatibility but are not implemented in this dependency-free runtime.

The agent loop treats an empty assistant response without tool calls as an
incomplete turn. It appends a short continuation prompt and retries until the
model either calls a tool, returns a non-empty final answer, or reaches
`max_steps`.
