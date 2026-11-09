"""The approval API behind the console: the round waiting for a decision, its checks and brief, the decision
record, and the approve or reject action. Identity comes from the gateway (an `X-User` and `X-Role` header set by
SSO in production); the agent's own identity can never approve."""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from agentrt.approvals import ApprovalError, Approvals, Person
from agentrt.ledger import Ledger
from agentrt.tasks import PersonTasks


class Decision(BaseModel):
    approve: bool
    note: str = ""
    sha256: str  # the file the person looked at; a mismatch is refused


def create_app(conn: sqlite3.Connection, rounds: dict[int, dict[str, Any]], clock=lambda: "2026-01-20") -> FastAPI:
    app = FastAPI(title="direct-mail-agent approvals")
    ledger, approvals, tasks = Ledger(conn), Approvals(conn, Ledger(conn)), PersonTasks(conn)

    @app.get("/rounds")
    def list_rounds() -> list[dict]:
        return [{"round": r, "letters": x["plan"]["letters"], "status": _status(x)} for r, x in sorted(rounds.items())]

    def _status(x: dict) -> str:
        if x.get("approval_id") is None:
            return "failed_checks"
        return approvals.get(x["approval_id"])["decision"] or "awaiting_approval"

    @app.get("/rounds/{r}")
    def get_round(r: int) -> dict:
        if r not in rounds:
            raise HTTPException(404, "no such round")
        x = rounds[r]
        return {**x, "status": _status(x)}

    @app.post("/rounds/{r}/decision")
    def decide(r: int, d: Decision, x_user: str = Header(...), x_role: str = Header(...)) -> dict:
        if r not in rounds:
            raise HTTPException(404, "no such round")
        x = rounds[r]
        if x.get("approval_id") is None:
            raise HTTPException(409, "the file failed its checks; there is nothing to approve")
        if d.sha256 != x["sha256"]:
            raise HTTPException(409, "the file changed since you opened it; reload")
        try:
            approvals.decide(
                x["approval_id"], person=Person(x_user, x_role), approve=d.approve, at=clock(), note=d.note
            )
        except ApprovalError as e:
            raise HTTPException(403, str(e)) from e
        return {"round": r, "status": _status(x)}

    @app.get("/ledger")
    def get_ledger(run: str | None = None) -> dict:
        ok, broken = ledger.verify()
        return {"intact": ok, "first_broken": broken, "entries": ledger.entries(run)}

    @app.get("/tasks")
    def get_tasks(status: str | None = "open") -> list[dict]:
        return tasks.list(status=status)

    return app
