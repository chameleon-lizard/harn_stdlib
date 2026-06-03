# Progress

## Working

- Replaced the previous multi-package dependency workspace with one stdlib
  package in `harn/`.
- Added OpenRouter chat-completions support through `urllib.request`.
- Set `deepseek-v4-flash` as the default model.
- Added cwd-scoped tools: `read`, `write`, `edit`, `bash`, `grep`, `find`,
  and `ls`.
- Added automatic `AGENTS.md` discovery plus explicit `--agents-file`.
- Added CLI support for direct prompts, stdin, `@file`, and `--prompt-file`.
- Added a dependency-free interactive TUI using stdlib `curses`, plus a
  line-mode fallback for terminals without curses.
- Added automatic TUI launch when `harn` runs without a prompt in an
  interactive terminal, plus explicit `--tui` and `--no-tui`.
- Added `harn_stdlib` as a compatibility alias for `harn`.
- Added the `harn-stdlib` console-script entry point targeting the same CLI as
  `harn`.
- Added `setup.cfg` metadata so source installs create both `harn` and
  `harn-stdlib` commands without runtime dependencies.
- Added original-Harn CLI compatibility parsing for common flags including
  `--print`, `--provider`, `--thinking`, `--tools`, `--list-models`,
  `--offline`, and `--no-context-files`.
- Fixed the agent loop so an empty model reply without tool calls no longer
  silently counts as a successful final answer.
- Added static stdlib tests in `agent_eval_tests/`.
- Added parity tests proving `harn` and `harn_stdlib` public API/module outputs
  match.
- Added parser/help tests for representative original-Harn compatibility flags.
- Added static tests for TUI dispatch and render helpers.
- Added a static regression test for empty no-tool model replies.
- Added optional live prompt evals using copied `AGENTS.md` and `DesignDoc.md`.
- Added an optional live `harn_stdlib` alias eval.
- Ran a dual DesignDoc implementation eval for `harn` and `harn_stdlib`; the
  setup was identical, but results were not equivalent. See
  `agent_eval_tests/design_doc_dual_eval_report.md`.
- Added module documentation in `harn/DOCUMENTATION.md` and
  `agent_eval_tests/DOCUMENTATION.md`.

## Planned or intentionally deferred

- Streaming output is not implemented.
- The stdlib TUI is intentionally simple: no mouse support, no streaming
  token rendering, no old rich theme system.
- Multi-provider SDK support is not implemented; OpenRouter is the supported
  path for this rewrite.
- Session persistence is not implemented.
- Structured edit diffs beyond exact text replacement are not implemented.

## Verification history

- `python3 -m compileall -q harn`
- `python3 -m harn --list-tools`
- `python3 -m harn --version`
- `python3 -m harn_stdlib --list-tools`
- `python3 -m harn_stdlib --version`
- `python3 -m harn --help`
- `python3 -m harn --tui --help`
- `python3 -m venv /tmp/harn-stdlib-venv && /tmp/harn-stdlib-venv/bin/python -m pip install --no-deps . && /tmp/harn-stdlib-venv/bin/harn --version && /tmp/harn-stdlib-venv/bin/harn-stdlib --version`
- `python3 -m unittest discover -s agent_eval_tests`
- Dual DesignDoc eval:
  - `harn`: 46/46 generated project tests passed, clean worktree.
  - `harn_stdlib`: 45/45 generated project tests passed, but agent hit
    `max_steps=40` and left a dirty worktree.
- `OPENROUTER_API_KEY=... python3 -m harn_stdlib --no-tools --model deepseek-v4-flash --max-steps 1 --max-tokens 80 --prompt 'Reply with exactly HARN_STDLIB_ALIAS_OK'`
- `RUN_OPENROUTER_EVAL=1 OPENROUTER_API_KEY=... python3 -m unittest discover -s agent_eval_tests -v`

Live OpenRouter verification passed on `deepseek-v4-flash` with the API key
provided through the environment.
