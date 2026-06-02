# harn_stdlib module documentation

`harn_stdlib` is a compatibility alias for `harn`.

The implementation intentionally re-exports from `harn` instead of duplicating
runtime code. This keeps `python -m harn`, `python -m harn_stdlib`, the `harn`
console script, and the `harn-stdlib` console script matched to the same agent
behavior, including original-Harn compatibility flag parsing.
