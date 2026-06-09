"""Skill discovery and prompt rendering for stdlib Harn."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class SkillError(RuntimeError):
    """Raised when a requested skill cannot be loaded."""


@dataclass(frozen=True)
class Skill:
    """One loaded skill instruction file."""

    name: str
    path: Path
    content: str


def default_skills_root() -> Path:
    """Return the default user skill directory."""

    return Path.home() / ".harn" / "skills"


def normalize_skill_name(name: str) -> str:
    """Return a stable display name for a skill path or identifier."""

    raw = name.strip().rstrip("/")
    if not raw:
        raise SkillError("Skill name cannot be empty")
    path = Path(raw)
    if path.name == "SKILL.md":
        return path.parent.name
    if path.suffix == ".md":
        return path.stem
    return path.name


def discover_skills(root: Path | None = None) -> list[Skill]:
    """Discover skills under the root directory without loading missing paths."""

    skill_root = root or default_skills_root()
    if not skill_root.is_dir():
        return []
    skills: list[Skill] = []
    for child in sorted(skill_root.iterdir(), key=lambda item: item.name.lower()):
        try:
            if child.is_dir():
                skill_file = child / "SKILL.md"
                if skill_file.is_file():
                    skills.append(read_skill_file(skill_file, child.name))
            elif child.is_file() and child.suffix == ".md":
                skills.append(read_skill_file(child, child.stem))
        except OSError:
            continue
    return skills


def resolve_skill_file(name_or_path: str, root: Path | None = None) -> Path:
    """Resolve a skill name, directory, markdown file, or explicit path."""

    raw = Path(name_or_path).expanduser()
    candidates: list[Path] = []
    if raw.is_absolute() or raw.exists():
        candidates.append(raw)
    else:
        skill_root = root or default_skills_root()
        candidates.extend(
            [
                skill_root / name_or_path / "SKILL.md",
                skill_root / f"{name_or_path}.md",
                skill_root / name_or_path,
            ]
        )
    for candidate in candidates:
        if candidate.is_dir():
            skill_file = candidate / "SKILL.md"
            if skill_file.is_file():
                return skill_file
        if candidate.is_file():
            return candidate
    raise SkillError(f"Skill not found: {name_or_path}")


def read_skill_file(path: Path, name: str | None = None) -> Skill:
    """Read a single skill markdown file."""

    if not path.is_file():
        raise SkillError(f"Skill file not found: {path}")
    try:
        content = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError as exc:
        raise SkillError(f"Cannot read skill file: {path}") from exc
    if not content:
        raise SkillError(f"Skill file is empty: {path}")
    return Skill(name=name or normalize_skill_name(str(path)), path=path, content=content)


def load_skills(names: list[str], root: Path | None = None) -> list[Skill]:
    """Load skills by name or path, preserving request order and de-duplicating."""

    loaded: list[Skill] = []
    seen: set[Path] = set()
    for raw_name in names:
        for name in split_skill_names(raw_name):
            path = resolve_skill_file(name, root)
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            loaded.append(read_skill_file(path, normalize_skill_name(name)))
    return loaded


def split_skill_names(raw: str) -> list[str]:
    """Split CLI/config/TUI skill input into names."""

    return [part.strip() for part in raw.replace(",", " ").split() if part.strip()]


def coerce_skill_names(value: object) -> list[str]:
    """Coerce a config value into a list of skill names."""

    if value is None:
        return []
    if isinstance(value, str):
        return split_skill_names(value)
    if isinstance(value, list):
        names: list[str] = []
        for item in value:
            if isinstance(item, str):
                names.extend(split_skill_names(item))
            else:
                raise SkillError("Config setting 'skills' must contain only strings")
        return names
    raise SkillError("Config setting 'skills' must be a string or list of strings")


def render_skills_prompt(skills: list[Skill]) -> str:
    """Render active skills for the system prompt."""

    if not skills:
        return ""
    parts = []
    for skill in skills:
        parts.append(f"## {skill.name}\nSource: {skill.path}\n\n{skill.content}")
    return "\n\n".join(parts)


def format_skill_list(skills: list[Skill], active_names: list[str] | None = None) -> str:
    """Return a human-readable skill list."""

    active = set(active_names or [])
    if not skills:
        return "No skills found."
    rows = []
    for skill in skills:
        marker = " *" if skill.name in active else ""
        rows.append(f"{skill.name}{marker}\t{skill.path}")
    return "\n".join(rows)
