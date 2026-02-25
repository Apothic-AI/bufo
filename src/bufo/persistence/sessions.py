"""SQLite-backed session metadata persistence."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bufo.paths import session_db_path


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class SessionRecord:
    id: int
    agent_name: str
    agent_identity: str
    agent_session_id: str | None
    title: str
    protocol: str
    created_at: str
    last_used_at: str
    metadata: dict[str, Any]


class SessionStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or session_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_name TEXT NOT NULL,
                    agent_identity TEXT NOT NULL,
                    agent_session_id TEXT,
                    title TEXT NOT NULL,
                    protocol TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_agent_pair
                ON sessions(agent_identity, agent_session_id)
                WHERE agent_session_id IS NOT NULL
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_sessions_last_used
                ON sessions(last_used_at DESC)
                """
            )

    def upsert(
        self,
        *,
        agent_name: str,
        agent_identity: str,
        agent_session_id: str | None,
        title: str,
        protocol: str,
        metadata: dict[str, Any],
    ) -> int:
        now = _utc_now()
        metadata_json = json.dumps(metadata, sort_keys=True)

        with self._connect() as conn:
            if agent_session_id:
                row = conn.execute(
                    """
                    SELECT id FROM sessions
                    WHERE agent_identity = ? AND agent_session_id = ?
                    """,
                    (agent_identity, agent_session_id),
                ).fetchone()
            else:
                row = None

            if row:
                session_id = int(row["id"])
                conn.execute(
                    """
                    UPDATE sessions
                    SET agent_name = ?, title = ?, protocol = ?,
                        last_used_at = ?, metadata_json = ?
                    WHERE id = ?
                    """,
                    (agent_name, title, protocol, now, metadata_json, session_id),
                )
                return session_id

            created_at = now
            cursor = conn.execute(
                """
                INSERT INTO sessions (
                    agent_name, agent_identity, agent_session_id,
                    title, protocol, created_at, last_used_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    agent_name,
                    agent_identity,
                    agent_session_id,
                    title,
                    protocol,
                    created_at,
                    now,
                    metadata_json,
                ),
            )
            return int(cursor.lastrowid)

    def get(self, session_id: int) -> SessionRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()

        return _row_to_record(row) if row else None

    def get_by_agent_pair(self, agent_identity: str, agent_session_id: str) -> SessionRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM sessions
                WHERE agent_identity = ? AND agent_session_id = ?
                """,
                (agent_identity, agent_session_id),
            ).fetchone()

        return _row_to_record(row) if row else None

    def recent(self, limit: int = 20) -> list[SessionRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM sessions ORDER BY last_used_at DESC LIMIT ?",
                (limit,),
            ).fetchall()

        return [_row_to_record(row) for row in rows]


def _row_to_record(row: sqlite3.Row) -> SessionRecord:
    return SessionRecord(
        id=int(row["id"]),
        agent_name=str(row["agent_name"]),
        agent_identity=str(row["agent_identity"]),
        agent_session_id=row["agent_session_id"],
        title=str(row["title"]),
        protocol=str(row["protocol"]),
        created_at=str(row["created_at"]),
        last_used_at=str(row["last_used_at"]),
        metadata=json.loads(str(row["metadata_json"])),
    )
