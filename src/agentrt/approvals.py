"""Approvals bound to the artefact a person saw.

An approval names the sha256 of the artefact, the role that must decide, and when it expires. It is valid only for
that exact artefact: change one record in the file and the approval no longer applies. The requester can never be
the approver, and the agent's own role can never approve.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from agentrt.ledger import Ledger


class ApprovalError(PermissionError):
    pass


@dataclass(frozen=True)
class Person:
    name: str
    role: str


class Approvals:
    AGENT_ROLES = frozenset({"agent"})

    def __init__(self, conn: sqlite3.Connection, ledger: Ledger):
        self.conn, self.ledger = conn, ledger

    def request(
        self, *, run: str, kind: str, artefact_sha: str, needs_role: str, requested_by: str, expires_at: str, at: str
    ) -> int:
        row = self.conn.execute(
            "select id from approvals where run = ? and kind = ? and artefact_sha = ? and decision is null",
            (run, kind, artefact_sha),
        ).fetchone()
        if row:
            return row["id"]
        cur = self.conn.execute(
            "insert into approvals (run, kind, artefact_sha, needs_role, requested_by, expires_at)"
            " values (?,?,?,?,?,?)",
            (run, kind, artefact_sha, needs_role, requested_by, expires_at),
        )
        self.ledger.record(
            at=at,
            run=run,
            step="approval",
            actor=requested_by,
            kind="approval_requested",
            decision={"id": cur.lastrowid, "kind": kind, "sha": artefact_sha, "needs": needs_role},
            reason="a person decides before anything leaves the building",
        )
        return cur.lastrowid

    def decide(self, approval_id: int, *, person: Person, approve: bool, at: str, note: str = "") -> None:
        row = self.conn.execute("select * from approvals where id = ?", (approval_id,)).fetchone()
        if row is None:
            raise ApprovalError(f"no approval {approval_id}")
        if row["decision"] is not None:
            raise ApprovalError("already decided")
        if person.role in self.AGENT_ROLES or person.name == row["requested_by"]:
            raise ApprovalError("the requester cannot approve its own request")
        if person.role != row["needs_role"]:
            raise ApprovalError(f"{row['kind']} needs {row['needs_role']}, not {person.role}")
        if at > row["expires_at"]:
            raise ApprovalError("the request has expired")
        decision = "approved" if approve else "rejected"
        self.conn.execute(
            "update approvals set decided_by = ?, decided_role = ?, decision = ?, decided_at = ?, note = ?"
            " where id = ?",
            (person.name, person.role, decision, at, note, approval_id),
        )
        self.ledger.record(
            at=at,
            run=row["run"],
            step="approval",
            actor=person.name,
            kind=f"approval_{decision}",
            decision={"id": approval_id, "sha": row["artefact_sha"]},
            reason=note or decision,
        )

    def valid(self, *, kind: str, artefact_sha: str, at: str) -> bool:
        row = self.conn.execute(
            "select * from approvals where kind = ? and artefact_sha = ? and decision = 'approved'"
            " order by id desc limit 1",
            (kind, artefact_sha),
        ).fetchone()
        return bool(row) and at <= row["expires_at"] and row["decided_role"] == row["needs_role"]

    def get(self, approval_id: int) -> dict:
        return dict(self.conn.execute("select * from approvals where id = ?", (approval_id,)).fetchone())
