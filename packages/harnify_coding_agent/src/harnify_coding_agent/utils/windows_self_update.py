"""Windows self-update helpers."""

from __future__ import annotations

import shutil
from pathlib import Path

_QUARANTINE_DIR_NAME = ".pi-native-quarantine"


def _get_quarantine_root(package_dir: str) -> Path | None:
    current = Path(package_dir).resolve()
    while True:
        if current.name.lower() == "node_modules":
            return current / _QUARANTINE_DIR_NAME
        if current.parent == current:
            return None
        current = current.parent


def cleanup_windows_self_update_quarantine(package_dir: str) -> None:
    quarantine_root = _get_quarantine_root(package_dir)
    if quarantine_root is None:
        return
    try:
        shutil.rmtree(quarantine_root)
    except FileNotFoundError:
        return
    except OSError:
        return


def quarantine_windows_native_dependencies(_package_dir: str) -> None:
    return None


cleanupWindowsSelfUpdateQuarantine = cleanup_windows_self_update_quarantine
quarantineWindowsNativeDependencies = quarantine_windows_native_dependencies

__all__ = ["cleanupWindowsSelfUpdateQuarantine", "quarantineWindowsNativeDependencies"]
