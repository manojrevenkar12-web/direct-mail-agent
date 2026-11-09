"""Tools behind permissions.

Every tool declares a scope. A caller acts as a role; the role's scopes come from `config/permissions.toml`, which
the agent cannot write. Tools with an external effect take an idempotency key: calling again with the same key
returns the first result and does not repeat the effect. Every call and every refusal goes to the decision record.
"""

from __future__ import annotations

import json
import sqlite3
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentrt.ledger import Ledger
from agentrt.store import dumps


class PermissionDenied(PermissionError):
    pass


@dataclass(frozen=True)
class Tool:
    name: str
    scope: str
    fn: Callable[..., Any]
    effect: bool = False


class Policy:
    def __init__(self, scopes: dict[str, set[str]]):
        self.scopes = scopes

    @classmethod
    def load(cls, path: Path) -> Policy:
        raw = tomllib.loads(path.read_text())
        return cls({role: set(v["scopes"]) for role, v in raw["roles"].items()})

    def allows(self, role: str, scope: str) -> bool:
        return scope in self.scopes.get(role, set())


class Toolbox:
    def __init__(self, conn: sqlite3.Connection, policy: Policy, ledger: Ledger, clock: Callable[[], str]):
        self.conn, self.policy, self.ledger, self.clock = conn, policy, ledger, clock
        self.tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def call(self, *, role: str, run: str, name: str, idempotency_key: str | None = None, **args: Any) -> Any:
        tool = self.tools[name]
        if not self.policy.allows(role, tool.scope):
            self.ledger.record(
                at=self.clock(),
                run=run,
                step=name,
                actor=role,
                kind="denied",
                decision={"tool": name, "scope": tool.scope},
                reason=f"role {role} has no scope {tool.scope}",
                inputs=args,
            )
            raise PermissionDenied(f"{role} may not call {name} (needs {tool.scope})")
        if tool.effect:
            if not idempotency_key:
                raise ValueError(f"{name} has an external effect and needs an idempotency key")
            row = self.conn.execute("select result from effects where key = ?", (idempotency_key,)).fetchone()
            if row:
                return json.loads(row["result"])
        out = tool.fn(**args)
        if tool.effect:
            self.conn.execute(
                "insert into effects (key, tool, run, result) values (?,?,?,?)",
                (idempotency_key, name, run, dumps(out)),
            )
            self.ledger.record(
                at=self.clock(),
                run=run,
                step=name,
                actor=role,
                kind="effect",
                decision={"tool": name, "key": idempotency_key, "result": out},
                reason="tool call with an external effect",
                inputs=args,
            )
        return out
