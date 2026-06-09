"""Persistent session storage for the stdlib Harn TUI."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


class SessionError(RuntimeError):
    """Raised when a persisted session cannot be loaded or saved."""


def default_session_root() -> Path:
    """Return the default session directory."""

    return Path.home() / ".harn" / "sessions"


def now_iso() -> str:
    """Return a local ISO timestamp."""

    return datetime.now().astimezone().isoformat(timespec="microseconds")


def new_session_id() -> str:
    """Return a filesystem-safe session id."""

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def write_json(path: Path, data: dict[str, Any]) -> None:
    """Write JSON atomically enough for single-process CLI use."""

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


@dataclass
class SessionStore:
    """One persisted Harn TUI session folder."""

    path: Path
    session_id: str

    @classmethod
    def create(cls, *, root: Path | None = None, metadata: dict[str, Any] | None = None) -> "SessionStore":
        session_root = root or default_session_root()
        session_root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(session_root, 0o700)
        except OSError:
            pass

        session_id = new_session_id()
        path = session_root / session_id
        path.mkdir(parents=True, exist_ok=False)
        try:
            os.chmod(path, 0o700)
        except OSError:
            pass

        store = cls(path=path, session_id=session_id)
        store.write_metadata({"created_at": now_iso(), "updated_at": now_iso(), **(metadata or {})})
        return store

    @classmethod
    def open(cls, session_id: str, *, root: Path | None = None) -> "SessionStore":
        raw = Path(session_id).expanduser()
        path = raw if raw.is_absolute() or raw.exists() else (root or default_session_root()) / session_id
        if not path.is_dir():
            raise SessionError(f"Session not found: {session_id}")
        return cls(path=path, session_id=path.name)

    @classmethod
    def latest(cls, *, root: Path | None = None, exclude: str | None = None) -> "SessionStore | None":
        sessions = cls.list(root=root)
        for store in sorted(sessions, key=lambda item: item.updated_at(), reverse=True):
            if exclude and store.session_id == exclude:
                continue
            return store
        return None

    @classmethod
    def list(cls, *, root: Path | None = None) -> list["SessionStore"]:
        session_root = root or default_session_root()
        if not session_root.is_dir():
            return []
        stores: list[SessionStore] = []
        for child in session_root.iterdir():
            if child.is_dir():
                stores.append(cls(path=child, session_id=child.name))
        return stores

    def metadata_path(self) -> Path:
        return self.path / "metadata.json"

    def state_path(self) -> Path:
        return self.path / "state.json"

    def events_path(self) -> Path:
        return self.path / "events.jsonl"

    def transcript_path(self) -> Path:
        return self.path / "transcript.log"

    def metadata(self) -> dict[str, Any]:
        path = self.metadata_path()
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SessionError(f"Invalid metadata JSON in {path}") from exc
        if not isinstance(data, dict):
            raise SessionError(f"Session metadata must be an object: {path}")
        return data

    def updated_at(self) -> str:
        return str(self.metadata().get("updated_at") or "")

    def write_metadata(self, metadata: dict[str, Any]) -> None:
        write_json(self.metadata_path(), metadata)

    def touch(self) -> None:
        metadata = self.metadata()
        metadata["updated_at"] = now_iso()
        self.write_metadata(metadata)

    def save_state(self, messages: list[dict[str, Any]], entries: list[dict[str, Any]]) -> None:
        write_json(
            self.state_path(),
            {
                "session_id": self.session_id,
                "updated_at": now_iso(),
                "messages": messages,
                "entries": entries,
            },
        )
        self.touch()

    def load_state(self) -> dict[str, Any]:
        path = self.state_path()
        if not path.exists():
            raise SessionError(f"Session state is missing: {self.session_id}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SessionError(f"Invalid session state JSON in {path}") from exc
        if not isinstance(data, dict):
            raise SessionError(f"Session state must be an object: {path}")
        return data

    def append_event(self, role: str, content: str, metadata: dict[str, Any] | None = None) -> None:
        event = {
            "timestamp": now_iso(),
            "role": role,
            "content": content,
            **(metadata or {}),
        }
        self.events_path().parent.mkdir(parents=True, exist_ok=True)
        with self.events_path().open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        with self.transcript_path().open("a", encoding="utf-8") as handle:
            handle.write(f"[{event['timestamp']}] {role}> {content}\n\n")
        self.touch()
