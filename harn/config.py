"""Shared constants for the stdlib Harn runtime."""

from __future__ import annotations

import os

VERSION = "0.2.0"
DEFAULT_MODEL = os.environ.get("HARN_MODEL", "deepseek-v4-flash")
DEFAULT_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
DEFAULT_API_KEY_ENV = "OPENROUTER_API_KEY"
DEFAULT_TIMEOUT_SECONDS = 120
DEFAULT_MAX_STEPS = 8
DEFAULT_MAX_OUTPUT_CHARS = 12000

DEFAULT_TOOLS = ("read", "write", "edit", "bash", "grep", "find", "ls")

