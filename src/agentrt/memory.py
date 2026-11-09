"""Memory that persists between runs, versioned, with where each value came from.

Two namespaces with different rules:
- `facts/...` are written by code from results, or by people. The planner reads only these.
- `notes/...` are the model's own observations. They are kept and shown to people, never used to decide.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from agentrt.store import dumps

FACT_SOURCES = {"results", "person", "config"}
NOTE_SOURCES = {"agent_note"}


class MemoryRuleError(PermissionError):
    pass


class Memory:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def put(self, key: str, value: Any, *, provenance: str, run: str, at: str) -> int:
        if key.startswith("facts/") and provenance not in FACT_SOURCES:
            raise MemoryRuleError(f"{provenance!r} cannot write a fact ({key})")
        if key.startswith("notes/") and provenance not in NOTE_SOURCES | FACT_SOURCES:
            raise MemoryRuleError(f"unknown provenance {provenance!r}")
        if not key.startswith(("facts/", "notes/")):
            raise MemoryRuleError(f"memory keys live under facts/ or notes/, got {key!r}")
        row = self.conn.execute("select max(version) v from memory where key = ?", (key,)).fetchone()
        version = (row["v"] or 0) + 1
        self.conn.execute(
            "insert into memory (key, version, value, provenance, run, written_at) values (?,?,?,?,?,?)",
            (key, version, dumps(value), provenance, run, at),
        )
        return version

    def get(self, key: str, default: Any = None) -> Any:
        row = self.conn.execute(
            "select value from memory where key = ? order by version desc limit 1", (key,)
        ).fetchone()
        return json.loads(row["value"]) if row else default

    def facts(self) -> dict[str, Any]:
        rows = self.conn.execute(
            "select key, value from memory m where key like 'facts/%' and version ="
            " (select max(version) from memory where key = m.key)"
        )
        return {r["key"]: json.loads(r["value"]) for r in rows}

    def history(self, key: str) -> list[dict]:
        rows = self.conn.execute("select * from memory where key = ? order by version", (key,))
        return [{**dict(r), "value": json.loads(r["value"])} for r in rows]
