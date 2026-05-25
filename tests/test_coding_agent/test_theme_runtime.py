from __future__ import annotations

import copy
import importlib
import json
import time
from pathlib import Path
from types import SimpleNamespace

interactive_theme_module = importlib.import_module("harnify_coding_agent.modes.interactive.theme.theme")


def test_load_theme_falls_back_to_256color_when_truecolor_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        interactive_theme_module,
        "getCapabilities",
        lambda: type("Caps", (), {"trueColor": False})(),
    )

    loaded = interactive_theme_module.load_theme("dark")

    assert loaded.getColorMode() == "256color"
    assert loaded.getFgAnsi("accent").startswith("\x1b[38;5;")
    assert loaded.getBgAnsi("userMessageBg").startswith("\x1b[48;5;")


def test_theme_syntax_highlighting_and_language_detection(monkeypatch) -> None:
    monkeypatch.setattr(
        interactive_theme_module,
        "getCapabilities",
        lambda: type("Caps", (), {"trueColor": True})(),
    )
    loaded = interactive_theme_module.load_theme("dark")

    highlighted_lines = interactive_theme_module.highlight_code("const value = 1", "typescript")
    highlighted_text = loaded.syntax_highlight("const value = 1", "typescript")

    assert interactive_theme_module.get_language_from_path("src/example.tsx") == "typescript"
    assert interactive_theme_module.get_language_from_path("Dockerfile") == "dockerfile"
    assert any("\x1b[" in line for line in highlighted_lines)
    assert "\x1b[" in highlighted_text


def test_theme_watcher_reloads_custom_theme_file(monkeypatch, tmp_path: Path) -> None:
    custom_themes_dir = tmp_path / "themes"
    custom_themes_dir.mkdir()
    payload = copy.deepcopy(interactive_theme_module.load_theme_json("dark"))
    payload["name"] = "watch-test"
    payload["colors"]["accent"] = "#112233"
    theme_path = custom_themes_dir / "watch-test.json"
    theme_path.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(
        interactive_theme_module,
        "getCapabilities",
        lambda: type("Caps", (), {"trueColor": True})(),
    )
    monkeypatch.setattr(interactive_theme_module, "get_custom_themes_dir", lambda: str(custom_themes_dir))

    changes: list[str] = []
    interactive_theme_module.on_theme_change(lambda: changes.append(interactive_theme_module.theme.getFgAnsi("accent")))
    interactive_theme_module.init_theme("watch-test", True)

    try:
        assert interactive_theme_module.theme.getFgAnsi("accent") == "\x1b[38;2;17;34;51m"

        payload["colors"]["accent"] = "#334455"
        theme_path.write_text(json.dumps(payload), encoding="utf-8")

        deadline = time.time() + 3
        while time.time() < deadline:
            if interactive_theme_module.theme.getFgAnsi("accent") == "\x1b[38;2;51;68;85m":
                break
            time.sleep(0.05)

        assert interactive_theme_module.theme.getFgAnsi("accent") == "\x1b[38;2;51;68;85m"
        assert changes
    finally:
        interactive_theme_module.stop_theme_watcher()
        interactive_theme_module.init_theme("dark")


def test_load_theme_from_path_reports_missing_required_color_tokens(tmp_path: Path) -> None:
    theme_path = tmp_path / "invalid.json"
    theme_path.write_text(json.dumps({"name": "broken", "colors": {"accent": "#ffffff"}}), encoding="utf-8")

    try:
        interactive_theme_module.load_theme_from_path(str(theme_path))
    except ValueError as error:
        message = str(error)
    else:
        raise AssertionError("Expected load_theme_from_path to reject missing required colors")

    assert 'Invalid theme "' in message
    assert "Missing required color tokens:" in message
    assert "Please add these colors to your theme's \"colors\" object." in message
    assert "border" in message


def test_registered_theme_load_json_reads_source_but_load_theme_returns_registered_instance(
    monkeypatch,
    tmp_path: Path,
) -> None:
    custom_themes_dir = tmp_path / "themes"
    custom_themes_dir.mkdir()
    payload = copy.deepcopy(interactive_theme_module.load_theme_json("dark"))
    payload["name"] = "registered-theme"
    payload["colors"]["accent"] = "#112233"
    theme_path = tmp_path / "registered-theme.json"
    theme_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(interactive_theme_module, "get_custom_themes_dir", lambda: str(custom_themes_dir))

    registered_theme = interactive_theme_module.load_theme_from_path(str(theme_path))
    interactive_theme_module.set_registered_themes([registered_theme])

    payload["colors"]["accent"] = "#334455"
    theme_path.write_text(json.dumps(payload), encoding="utf-8")

    exported = interactive_theme_module.load_theme_json("registered-theme")
    loaded = interactive_theme_module.load_theme("registered-theme")

    assert exported["colors"]["accent"] == "#334455"
    assert loaded is registered_theme
    assert loaded.getFgAnsi("accent") == "\x1b[38;2;17;34;51m"


def test_theme_watcher_ignores_registered_theme_outside_custom_dir(monkeypatch, tmp_path: Path) -> None:
    custom_themes_dir = tmp_path / "themes"
    custom_themes_dir.mkdir()
    payload = copy.deepcopy(interactive_theme_module.load_theme_json("dark"))
    payload["name"] = "external-theme"
    payload["colors"]["accent"] = "#112233"
    theme_path = tmp_path / "external-theme.json"
    theme_path.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(
        interactive_theme_module,
        "getCapabilities",
        lambda: type("Caps", (), {"trueColor": True})(),
    )
    monkeypatch.setattr(interactive_theme_module, "get_custom_themes_dir", lambda: str(custom_themes_dir))

    registered_theme = interactive_theme_module.load_theme_from_path(str(theme_path))
    interactive_theme_module.set_registered_themes([registered_theme])
    interactive_theme_module.init_theme("external-theme", True)

    try:
        assert interactive_theme_module.theme.getFgAnsi("accent") == "\x1b[38;2;17;34;51m"
        payload["colors"]["accent"] = "#334455"
        theme_path.write_text(json.dumps(payload), encoding="utf-8")
        time.sleep(0.3)
        assert interactive_theme_module.theme.getFgAnsi("accent") == "\x1b[38;2;17;34;51m"
    finally:
        interactive_theme_module.stop_theme_watcher()
        interactive_theme_module.init_theme("dark")
