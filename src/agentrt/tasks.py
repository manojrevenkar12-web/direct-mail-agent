"""Durable steps and tasks for people.

A run is a list of named steps. A finished step is never run again: after a crash the run resumes from the first
unfinished step and gets the stored outputs of the finished ones. Tasks for people (confirm a direction, look at an
anomaly, process an objection) are deduplicated, so a resumed run does not ask twice.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from typing import Any

from agentrt.store import dumps


class Steps:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def run(self, run: str, step: str, fn: Callable[[], Any]) -> Any:
        row = self.conn.execute("select status, output from steps where run = ? and step = ?", (run, step)).fetchone()
        if row and row["status"] == "done":
            return json.loads(row["output"])
        self.conn.execute(
            "insert into steps (run, step, status) values (?,?, 'started')"
            " on conflict (run, step) do update set status = 'started'",
            (run, step),
        )
        out = fn()
        self.conn.execute(
            "update steps set status = 'done', output = ? where run = ? and step = ?", (dumps(out), run, step)
        )
        return json.loads(dumps(out))

    def status(self, run: str) -> dict[str, str]:
        return {r["step"]: r["status"] for r in self.conn.execute("select * from steps where run = ?", (run,))}


class PersonTasks:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def open(self, *, run: str, owner_role: str, kind: str, payload: dict, dedupe: str) -> int:
        row = self.conn.execute("select id from person_tasks where dedupe = ?", (dedupe,)).fetchone()
        if row:
            return row["id"]
        cur = self.conn.execute(
            "insert into person_tasks (run, owner_role, kind, payload, status, dedupe) values (?,?,?,?, 'open', ?)",
            (run, owner_role, kind, dumps(payload), dedupe),
        )
        return cur.lastrowid

    def close(self, task_id: int, status: str = "done") -> None:
        self.conn.execute("update person_tasks set status = ? where id = ?", (status, task_id))

    def list(self, run: str | None = None, status: str | None = None) -> list[dict]:
        q, args = "select * from person_tasks where 1=1", []
        if run:
            q, args = q + " and run = ?", [*args, run]
        if status:
            q, args = q + " and status = ?", [*args, status]
        return [{**dict(r), "payload": json.loads(r["payload"])} for r in self.conn.execute(q + " order by id", args)]
