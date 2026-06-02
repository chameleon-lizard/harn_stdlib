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

