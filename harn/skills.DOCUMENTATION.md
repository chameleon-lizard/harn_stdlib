# harn.skills module documentation

`harn.skills` is the stdlib-only skill loader.

## Storage

The default skill root is `$HOME/.harn/skills`. Harn recognizes:

- `$HOME/.harn/skills/<name>/SKILL.md`
- `$HOME/.harn/skills/<name>.md`
- explicit absolute or relative paths passed through `--skill` or `/skill`

`SKILL.md` files are read as UTF-8 text. Empty or missing files raise
`SkillError`.

## Runtime Use

`discover_skills()` lists available skills. `load_skills()` loads requested
skills by name or path and de-duplicates repeated files. `render_skills_prompt()`
formats active skills into the system prompt.

CLI activation is handled with `--skill`, `--skills-dir`, `--list-skills`,
`HARN_SKILLS`, `HARN_SKILLS_DIR`, and config keys `skills` and `skills_dir`.
The TUI uses `/skills`, `/skill <name>`, and `/skill off`.
