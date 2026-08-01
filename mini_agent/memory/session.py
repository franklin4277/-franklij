"""Session management — file-backed, shared by CLI / API / Web.

Public API:
    Message: role + content + timestamp
    Session: token + chat_id + workspace + history
    SessionStore: CRUD + atomic persistence
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from ..connectors.sqlbot import SqlBotClient

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """A message in session history."""

    role: str  # "user" | "assistant"
    content: str
    timestamp: str
    sql: str | None = None
    record_id: int | None = None


@dataclass
class Session:
    """A SQLBot-backed chat session.

    One session = one SQLBot chat_id (multi-turn context lives server-side).
    """

    id: str
    token: str
    chat_id: int
    workspace_id: str = "1"
    default_datasource_id: int | None = None
    workspace: Path = field(default_factory=Path)
    history: list[Message] = field(default_factory=list)
    created_at: str = ""
    last_used_at: str = ""

    def is_valid(self) -> bool:
        return bool(self.token) and self.chat_id > 0

    def touch(self) -> None:
        self.last_used_at = datetime.now().isoformat()


class SessionStore:
    """File-backed session store. Single instance per process."""

    def __init__(self, sqlbot: SqlBotClient, base_dir: str | Path):
        self.sqlbot = sqlbot
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, Session] = {}

    # ----- CRUD -----
    def create(self, *, default_datasource_id: int | None = None) -> Session:
        """Login to SQLBot + start chat session. Persist to disk."""
        sess_dir = self.base_dir / f"sess-{uuid.uuid4().hex[:12]}"
        sess_dir.mkdir(parents=True, exist_ok=True)

        token = self.sqlbot.login()
        token, chat_id = self.sqlbot.start_session(token)
        now = datetime.now().isoformat()
        sess = Session(
            id=sess_dir.name,
            token=token,
            chat_id=chat_id,
            workspace_id=self.sqlbot.cfg.workspace_id,
            default_datasource_id=default_datasource_id or self.sqlbot.cfg.default_datasource_id,
            workspace=sess_dir,
            created_at=now,
            last_used_at=now,
        )
        self._save(sess)
        self._cache[sess.id] = sess
        return sess

    def get(self, session_id: str) -> Session:
        """Load from cache or disk. Raises KeyError if not found."""
        if session_id in self._cache:
            return self._cache[session_id]
        sess = self._load_from_disk(session_id)
        self._cache[session_id] = sess
        return sess

    def destroy(self, session_id: str) -> None:
        sess = self._cache.pop(session_id, None)
        if sess and sess.workspace.exists():
            import shutil
            shutil.rmtree(sess.workspace, ignore_errors=True)

    def list_ids(self) -> list[str]:
        """Return IDs of sessions with valid session.json (recovers from partial dirs)."""
        out: list[str] = []
        for p in self.base_dir.iterdir():
            if p.is_dir() and p.name.startswith("sess-") and (p / "session.json").exists():
                out.append(p.name)
        return out

    # ----- History -----
    def append_history(
        self, session_id: str, role: str, content: str, **extra
    ) -> None:
        sess = self.get(session_id)
        msg = Message(
            role=role,
            content=content,
            timestamp=datetime.now().isoformat(),
            **extra,
        )
        sess.history.append(msg)
        self._save(sess)

    def save(self, session: Session) -> None:
        """Persist session (after touch / mutations)."""
        self._save(session)

    # ----- Internals -----
    def _save(self, sess: Session) -> None:
        """Atomic write: tmp file + rename."""
        path = sess.workspace / "session.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(asdict(sess), default=str, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(path)

    def _load_from_disk(self, session_id: str) -> Session:
        path = self.base_dir / session_id / "session.json"
        if not path.exists():
            raise KeyError(f"session not found: {session_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        data["workspace"] = Path(data["workspace"])
        data["history"] = [Message(**m) for m in data.get("history", [])]
        return Session(**data)


__all__ = ["Message", "Session", "SessionStore"]