# harn module documentation

`harn` is a dependency-free Python package that runs a compact coding agent
against OpenRouter's OpenAI-compatible chat-completions API.

## Modules

- `config.py` contains defaults such as `deepseek-v4-flash`,
  `OPENROUTER_API_KEY`, timeout, max steps, and tool names.
- `client.py` implements the OpenRouter HTTP client with `urllib.request`.
- `tools.py` exposes filesystem and shell tools: `read`, `write`, `edit`,
  `bash`, `grep`, `find`, and `ls`.
- `prompts.py` builds the system prompt and auto-loads the nearest
  `AGENTS.md`.
- `agent.py` runs the model/tool loop until the assistant returns a final
  answer.
- `cli.py` provides the `python -m harn` command-line interface.

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

The CLI accepts common original-Harn flags such as `--print`, `--provider`,
`--thinking`, `--tools/-t`, `--no-tools/-nt`, `--list-models`, `--offline`, and
`--no-context-files/-nc`. Unsupported stateful subsystems are parsed for
compatibility but are not implemented in this dependency-free runtime.

The agent loop treats an empty assistant response without tool calls as an
incomplete turn. It appends a short continuation prompt and retries until the
model either calls a tool, returns a non-empty final answer, or reaches
`max_steps`.
