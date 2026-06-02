"""Optional live OpenRouter checks using AGENTS.md and DesignDoc.md prompts."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROMPT_DIR = Path(os.environ.get("HARN_EVAL_PROMPT_DIR", ROOT / "agent_eval_tests" / "prompts"))
MODEL = os.environ.get("HARN_MODEL", "deepseek-v4-flash")
LIVE_ENABLED = os.environ.get("RUN_OPENROUTER_EVAL") == "1"


def _require_live() -> None:
    if not LIVE_ENABLED:
        raise unittest.SkipTest("set RUN_OPENROUTER_EVAL=1 to run live OpenRouter evals")
    if not os.environ.get("OPENROUTER_API_KEY"):
        raise unittest.SkipTest("set OPENROUTER_API_KEY to run live OpenRouter evals")


def _run_harn(
    args: list[str],
    *,
    cwd: Path = ROOT,
    module: str = "harn",
    timeout: int = 180,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("HARN_MODEL", MODEL)
    return subprocess.run(
        [sys.executable, "-m", module, *args],
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


class LivePromptEvalTests(unittest.TestCase):
    def test_harn_stdlib_alias_live_call_matches_runtime(self) -> None:
        _require_live()
        completed = _run_harn(
            [
                "--no-tools",
                "--model",
                MODEL,
                "--max-steps",
                "1",
                "--max-tokens",
                "80",
                "--prompt",
                "Reply with exactly HARN_STDLIB_ALIAS_OK",
            ],
            module="harn_stdlib",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("HARN_STDLIB_ALIAS_OK", completed.stdout)

    def test_agents_prompt_is_understood(self) -> None:
        _require_live()
        prompt = PROMPT_DIR / "AGENTS.md"
        completed = _run_harn(
            [
                "--no-tools",
                "--model",
                MODEL,
                "--max-steps",
                "1",
                "--max-tokens",
                "500",
                "--prompt-file",
                str(prompt),
                "-p",
                "Read the attached AGENTS.md and return three short bullets: documentation, git, productivity.",
            ]
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        output = completed.stdout.lower()
        self.assertIn("documentation", output)
        self.assertIn("git", output)
        self.assertIn("product", output)

    def test_design_doc_prompt_is_understood(self) -> None:
        _require_live()
        prompt = PROMPT_DIR / "DesignDoc.md"
        completed = _run_harn(
            [
                "--no-tools",
                "--model",
                MODEL,
                "--max-steps",
                "1",
                "--max-tokens",
                "700",
                "--prompt-file",
                str(prompt),
                "-p",
                "Read the attached DesignDoc.md. Name five core invariants of the autoresearch loop.",
            ]
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        output = completed.stdout.lower()
        for expected in ("cache", "append", "held", "single", "crash"):
            self.assertIn(expected, output)

    def test_agent_can_use_tools_to_create_file(self) -> None:
        _require_live()
        agents_prompt = PROMPT_DIR / "AGENTS.md"
        with tempfile.TemporaryDirectory(prefix="harn-eval-") as raw_tmp:
            tmp = Path(raw_tmp)
            completed = _run_harn(
                [
                    "--cwd",
                    str(tmp),
                    "--agents-file",
                    str(agents_prompt),
                    "--model",
                    MODEL,
                    "--max-steps",
                    "5",
                    "-p",
                    "Use tools to create file agent_result.txt containing exactly HARN_STDLIB_OK. Then reply done.",
                ],
                cwd=ROOT,
                timeout=240,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result_file = tmp / "agent_result.txt"
            self.assertTrue(result_file.is_file(), completed.stdout)
            self.assertEqual("HARN_STDLIB_OK", result_file.read_text(encoding="utf-8").strip())


if __name__ == "__main__":
    unittest.main()
