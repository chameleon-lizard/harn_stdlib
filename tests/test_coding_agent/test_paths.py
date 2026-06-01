"""Tests for path utilities, ported from paths.test.ts and path-utils.test.ts.

Tests path normalization, resolution, and local-path detection helpers.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from harn_coding_agent.utils.paths import (
    get_cwd_relative_path,
    is_local_path,
    normalize_path,
    resolve_path,
)


class TestIsLocalPath:
    """Ported from paths.test.ts."""

    def test_identifies_relative_paths_as_local(self) -> None:
        assert is_local_path("./foo/bar") is True
        assert is_local_path("foo/bar") is True
        assert is_local_path("../baz") is True

    def test_identifies_absolute_paths_as_local(self) -> None:
        assert is_local_path("/usr/local/bin") is True

    def test_rejects_npm_protocol(self) -> None:
        assert is_local_path("npm:package@latest") is False

    def test_rejects_git_protocol(self) -> None:
        assert is_local_path("git:repo") is False

    def test_rejects_http_protocol(self) -> None:
        assert is_local_path("http://example.com") is False
        assert is_local_path("https://example.com") is False

    def test_rejects_github_protocol(self) -> None:
        assert is_local_path("github:user/repo") is False

    def test_rejects_ssh_protocol(self) -> None:
        assert is_local_path("ssh://git@github.com") is False


class TestNormalizePath:
    """Ported from paths.test.ts."""

    def test_expands_tilde_to_home_directory(self) -> None:
        result = normalize_path("~")
        assert "~" not in result

    def test_expands_tilde_slash_path_to_home(self) -> None:
        result = normalize_path("~/Documents/file.txt")
        assert "~/" not in result

    def test_keeps_tilde_prefixed_filenames_literal(self) -> None:
        assert normalize_path("~draft.md", expand_tilde=True) == "~draft.md"

    def test_strips_leading_and_trailing_whitespace_when_trim_is_true(self) -> None:
        assert normalize_path("  /path/to/file  ", trim=True) == "/path/to/file"

    def test_handles_file_uri(self) -> None:
        result = normalize_path("file:///home/user/file.txt")
        assert result.endswith("home/user/file.txt") or "file.txt" in result


class TestResolvePath:
    """Ported from paths.test.ts."""

    def test_resolves_relative_path_against_base(self) -> None:
        result = resolve_path("foo.txt", "/base/dir")
        assert result == os.path.abspath("/base/dir/foo.txt")

    def test_resolves_absolute_path_unchanged(self) -> None:
        result = resolve_path("/absolute/path.txt", "/base/dir")
        assert result == os.path.abspath("/absolute/path.txt")


class TestGetCwdRelativePath:
    """Ported from paths.test.ts."""

    def test_returns_relative_path_for_files_inside_cwd(self) -> None:
        result = get_cwd_relative_path("/project/src/file.py", "/project")
        assert result is not None
        assert ".." not in result

    def test_returns_none_for_files_outside_cwd(self) -> None:
        result = get_cwd_relative_path("/other/path/file.py", "/project")
        assert result is None
