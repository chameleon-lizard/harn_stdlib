"""Static and local checks that require no network or external packages."""

from __future__ import annotations

import ast
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARN_DIR = ROOT / "harn"

BANNED_IMPORTS = {
    "aiofiles",
    "anthropic",
    "blessed",
    "boto3",
    "click",
    "filelock",
    "google",
    "httpx",
    "json_repair",
    "jsonlines",
    "jsonschema",
    "markdown_it",
    "mistralai",
    "openai",
    "pathspec",
    "psutil",
    "pydantic",
    "pygments",
    "pytest",
    "rapidfuzz",
    "requests",
    "rich",
    "ruamel",
    "term_image",
    "wcmatch",
    "websockets",
    "wcwidth",
}


class StaticStdlibTests(unittest.TestCase):
    def test_pyproject_declares_no_runtime_dependencies(self) -> None:
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("dependencies = []", text)
        self.assertNotIn("[tool.uv.workspace]", text)
        self.assertNotIn("[dependency-groups]", text)
        self.assertNotIn("pytest", text)

    def test_runtime_python_files_do_not_import_known_external_packages(self) -> None:
        offenders: list[str] = []
        for path in HARN_DIR.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name.split(".", 1)[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = [node.module.split(".", 1)[0]]
                else:
                    continue
                for name in names:
                    if name in BANNED_IMPORTS:
                        offenders.append(f"{path.name}: {name}")
        self.assertEqual([], offenders)

    def test_cli_lists_tools_with_system_python(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "harn", "--list-tools"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        for tool in ("read", "write", "edit", "bash", "grep", "find", "ls"):
            self.assertIn(tool, completed.stdout)


if __name__ == "__main__":
    unittest.main()

