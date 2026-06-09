"""User configuration loading for Harn."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_PATH = Path.home() / ".harn" / "harn.json"


class SettingsError(RuntimeError):
    """Raised when the user configuration file cannot be loaded."""


def default_config_path() -> Path:
    """Return the default user config path."""

    return Path.home() / ".harn" / "harn.json"


def load_settings(path: Path | None = None) -> dict[str, Any]:
    """Load Harn JSON settings.

    The default path is ``$HOME/.harn/harn.json``. Missing files are allowed
    and return an empty dict.
    """

    config_path = path or default_config_path()
    if not config_path.exists():
        return {}
    if not config_path.is_file():
        raise SettingsError(f"Config path is not a file: {config_path}")
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SettingsError(f"Invalid JSON in {config_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SettingsError(f"Config must be a JSON object: {config_path}")
    return data


def string_setting(settings: dict[str, Any], *names: str) -> str | None:
    """Return the first non-empty string setting from a list of keys."""

    for name in names:
        value = settings.get(name)
        if isinstance(value, str) and value:
            return value
    return None


def int_setting(settings: dict[str, Any], name: str, default: int) -> int:
    """Return an integer setting, accepting JSON numbers or numeric strings."""

    value = settings.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise SettingsError(f"Config setting {name!r} must be an integer") from exc


def float_setting(settings: dict[str, Any], name: str, default: float) -> float:
    """Return a float setting, accepting JSON numbers or numeric strings."""

    value = settings.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise SettingsError(f"Config setting {name!r} must be a number") from exc
