"""One SQLite connection per run directory. PostgreSQL in production; the SQL is plain enough for both."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

SCHEMA = """
create table if not exists decisions (
  seq integer primary key, at text not null, run text not null, step text not null, actor text not null,
  kind text not null, decision text not null, reason text not null, inputs text not null,
  prev text not null, hash text not null
);
create table if not exists memory (
  key text not null, version integer not null, value text not null, provenance text not null,
  run text not null, written_at text not null, primary key (key, version)
);
create table if not exists steps (
  run text not null, step text not null, status text not null, output text,
  primary key (run, step)
);
create table if not exists person_tasks (
  id integer primary key, run text not null, owner_role text not null, kind text not null,
  payload text not null, status text not null, dedupe text not null unique
);
create table if not exists approvals (
  id integer primary key, run text not null, kind text not null, artefact_sha text not null,
  needs_role text not null, requested_by text not null, expires_at text not null,
  decided_by text, decided_role text, decision text, decided_at text, note text
);
create table if not exists effects (
  key text primary key, tool text not null, run text not null, result text not null
);
"""


def connect(path: str | Path = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def dumps(x: Any) -> str:
    return json.dumps(x, sort_keys=True, separators=(",", ":"), default=_plain)


def _plain(x: Any) -> Any:
    if hasattr(x, "item"):
        return x.item()
    if hasattr(x, "tolist"):
        return x.tolist()
    if hasattr(x, "model_dump"):
        return x.model_dump(mode="json")
    raise TypeError(f"not JSON serialisable: {type(x).__name__}")
