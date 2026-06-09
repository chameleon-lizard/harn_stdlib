# agent_eval_tests module documentation

This directory contains the test suite for the stdlib rewrite.

## Static tests

`test_static_stdlib.py` runs without network access or third-party packages. It
checks that `pyproject.toml` declares no runtime dependencies, that `harn/*.py`
and `harn_stdlib/*.py` do not import the known dependency packages from the
previous implementation, that `python -m harn --list-tools` works under the
system Python, and that `harn` and `harn_stdlib` match on public API, tool list,
and version output. It also checks representative original-Harn compatibility
flags in the stdlib parser and help output, plus the empty no-tool reply
regression path in the agent loop, TUI dispatch/render helpers, TUI line-editing
controls, slash-command discovery, user config option resolution, reasoning
trace preservation, command-result traces, and edit-diff traces.

`design_doc_dual_eval_report.md` records a live dual-agent implementation run
against `DesignDoc.md`. It is a report artifact, not a unit test.

Run:

```bash
python -m unittest discover -s agent_eval_tests
```

## Live prompt evals

`test_prompt_eval.py` is skipped unless `RUN_OPENROUTER_EVAL=1` and
`OPENROUTER_API_KEY` are set. It uses the prompt copies in
`agent_eval_tests/prompts/`:

- `AGENTS.md` checks whether the agent can read and summarize the project
  instructions.
- `DesignDoc.md` checks whether the agent can extract core autoresearch-loop
  invariants.
- A tool-use smoke test checks whether the agent can create a file in a
  temporary working directory.
- A `harn_stdlib` alias smoke test checks whether the alias reaches the same
  OpenRouter runtime.

Run:

```bash
RUN_OPENROUTER_EVAL=1 OPENROUTER_API_KEY=... python -m unittest discover -s agent_eval_tests
```
