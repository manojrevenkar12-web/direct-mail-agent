"""The decision record: every decision, who or what made it, why, and a digest of what it was based on.

Entries are hash-chained, so editing or deleting one breaks `verify()` from that entry on.
"""

from __future__ import annotations

import hashlib
import sqlite3
from typing import Any

from agentrt.store import dumps

GENESIS = "0" * 64


def digest(x: Any) -> str:
    return hashlib.sha256(dumps(x).encode()).hexdigest()


class Ledger:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def _last(self) -> str:
        row = self.conn.execute("select hash from decisions order by seq desc limit 1").fetchone()
        return row["hash"] if row else GENESIS

    def record(
        self, *, at: str, run: str, step: str, actor: str, kind: str, decision: Any, reason: str, inputs: Any = None
    ) -> str:
        if not reason.strip():
            raise ValueError("every decision needs a reason")
        prev = self._last()
        body = {
            "at": at,
            "run": run,
            "step": step,
            "actor": actor,
            "kind": kind,
            "decision": decision,
            "reason": reason,
            "inputs": digest(inputs),
            "prev": prev,
        }
        h = digest(body)
        self.conn.execute(
            "insert into decisions (at, run, step, actor, kind, decision, reason, inputs, prev, hash)"
            " values (?,?,?,?,?,?,?,?,?,?)",
            (at, run, step, actor, kind, dumps(decision), reason, body["inputs"], prev, h),
        )
        return h

    def entries(self, run: str | None = None) -> list[dict]:
        q = "select * from decisions" + (" where run = ?" if run else "") + " order by seq"
        return [dict(r) for r in self.conn.execute(q, (run,) if run else ())]

    def verify(self) -> tuple[bool, int | None]:
        """(True, None) when intact, else (False, seq of the first entry that no longer matches)."""
        import json

        prev = GENESIS
        for r in self.conn.execute("select * from decisions order by seq"):
            body = {
                "at": r["at"],
                "run": r["run"],
                "step": r["step"],
                "actor": r["actor"],
                "kind": r["kind"],
                "decision": json.loads(r["decision"]),
                "reason": r["reason"],
                "inputs": r["inputs"],
                "prev": prev,
            }
            if r["prev"] != prev or digest(body) != r["hash"]:
                return False, r["seq"]
            prev = r["hash"]
        return True, None
