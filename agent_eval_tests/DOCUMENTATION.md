# agent_eval_tests module documentation

This directory contains the test suite for the stdlib rewrite.

## Static tests

`test_static_stdlib.py` runs without network access or third-party packages. It
checks that `pyproject.toml` declares no runtime dependencies, that `harn/*.py`
does not import the known dependency packages from the previous implementation,
and that `python -m harn --list-tools` works under the system Python.

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

Run:

```bash
RUN_OPENROUTER_EVAL=1 OPENROUTER_API_KEY=... python -m unittest discover -s agent_eval_tests
```

