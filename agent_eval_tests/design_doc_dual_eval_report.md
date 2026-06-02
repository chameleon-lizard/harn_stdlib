# DesignDoc dual-agent implementation eval

Date: 2026-06-02

This report compares two live implementation runs of the same task:

- `python3 -m harn`
- `python3 -m harn_stdlib`

Both runs started from the same template repository at
`/tmp/harn-design-doc-dual-eval/template`, with initial commit `a2522fe`.
The template contained only:

- `AGENTS.md`
- `DesignDoc.md`
- `README.md`

Both runs used:

- model: `deepseek-v4-flash`
- temperature: `0`
- max steps: `40`
- max tokens: `6000`
- same implementation prompt
- same `AGENTS.md` and `DesignDoc.md`

The only intentional differences were the module entrypoint and `--cwd`.
The API key was supplied through the environment and is not stored here.

## Result summary

| Check | `harn` | `harn_stdlib` |
|---|---:|---:|
| Process exit | `0` | `1`, max steps reached |
| Package created | yes | yes |
| `python -m autoresearch_loop --help` | passes | passes |
| CLI commands `run/report/reset/score` | present | present |
| DesignDoc `--max-iters` | missing | missing |
| DesignDoc `--limit` | missing | missing |
| Deterministic `sha256(...)[0:16]` hash | present | present |
| train/dev/test split | present | present |
| cache under state/cache/hash | present | present |
| append-only `experiments.jsonl` | present | present |
| `notes.md` notebook | present | present |
| Stage A/B/C/M abstractions | present | present |
| Tests present | yes | yes, but uncommitted |
| Tests passing | 46/46 | 45/45 |
| `WIKI.md` / `PROGRESS.md` / `OPS.md` / module docs | present | missing |
| Git commits beyond initial | 5 | 1 |
| Clean worktree | yes | no |

## Conclusion

The runs were identical in setup, but the outputs were not roughly equivalent.

`harn` produced a more complete implementation: runnable CLI, tests, docs,
multiple commits, and clean worktree. It still missed the exact DesignDoc CLI
flags `--max-iters` and `--limit`, using `--batches` instead.

`harn_stdlib` produced a runnable core package and passing tests, but the agent
hit `max_steps=40` before finishing. It left tests uncommitted, did not create
the required docs, and left a dirty worktree. It also missed `--max-iters` and
`--limit`.

The evaluation therefore does not prove that `harn` and `harn-stdlib` produce
the same implementation results on this DesignDoc task. It proves only that
both can make meaningful progress from the same prompt, with materially
different completeness.

