"""The round: read results, notice anomalies, read the inbox, plan, build and check the file, write the brief, ask a
person to approve, and release to the printer only with that person's approval of that exact file.

Each step is durable. A crash resumes from the first unfinished step, the model is not asked again for something it
already answered, and the printer never receives the same file twice.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from agentrt.approvals import Approvals
from agentrt.ledger import Ledger
from agentrt.memory import Memory
from agentrt.tasks import PersonTasks, Steps
from agentrt.tools import Policy, Tool, Toolbox
from mailagent import anomalies, brief, directives, learning, mailfile, objection, optimise, rules, settings
from mailagent.ports import CreativeRegister, Inbox, Models, Printer, Reader, Results, Warehouse
from mailagent.schema import CellPlan, Check, Directive, Message, Plan, Usage


@dataclass(frozen=True)
class Mode:
    """What varies between the policies the evaluation compares. The agent is the default."""

    name: str = "agent"
    selection: str = "optimiser"  # "optimiser" or "top_score" (today's process)
    learner: str = "response"  # "response", "response_no_delay", "incremental", "none"
    reader: bool = True  # the model reads the inbox, triages anomalies and writes the brief
    guarded: bool = True  # directions validated, file checked; False only to show what goes wrong
    holdout: bool = True
    holdout_share: float | None = None  # None: from config


@dataclass
class RoundOutcome:
    round: int
    plan: Plan
    file: mailfile.MailFile
    checks: list[Check]
    brief: str | None
    brief_attempts: int
    brief_fallback: bool
    directions: list[dict]
    anomalies: list[dict]
    usage: Usage
    approval_id: int | None
    suppressed: dict[str, int]
    eligible: int
    person_tasks: list[dict] = field(default_factory=list)


class RoundAgent:
    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        warehouse: Warehouse,
        models: Models,
        results: Results,
        inbox: Inbox,
        register: CreativeRegister,
        printer: Printer,
        reader: Reader | None,
        mode: Mode = Mode(),
        seed: int = 7,
    ):
        self.conn, self.mode, self.seed = conn, mode, seed
        self.warehouse, self.models, self.results = warehouse, models, results
        self.inbox, self.register, self.printer, self.reader = inbox, register, printer, reader
        self.ledger = Ledger(conn)
        self.memory = Memory(conn)
        self.steps = Steps(conn)
        self.tasks = PersonTasks(conn)
        self.approvals = Approvals(conn, self.ledger)
        self._now, self._run = "2026-01-01", "setup"
        self.toolbox = Toolbox(conn, Policy.load(settings.CONFIG / "permissions.toml"), self.ledger, lambda: self._now)
        self.toolbox.register(Tool("printer.submit", "printer.release", self._submit, effect=True))
        self.toolbox.register(Tool("suppression.add", "suppression.write", lambda **kw: kw, effect=True))
        self.toolbox.register(Tool("memory.note", "memory.note", self._note))

    # -- tools ---------------------------------------------------------------------------------------------------
    def _submit(self, *, round: int, sha256: str, letters: int, mail_codes: list[str], withdraw: list[int]) -> dict:
        return self.printer.submit(
            round=round, sha256=sha256, letters=letters, mail_codes=mail_codes, withdraw=withdraw
        )

    def _note(self, *, key: str, text: str) -> int:
        return self.memory.put(f"notes/{key}", text, provenance="agent_note", run=self._run, at=self._now)

    # -- the round -----------------------------------------------------------------------------------------------
    def plan_round(
        self,
        r: int,
        form_directions: list[dict] | None = None,
        *,
        reuse: RoundOutcome | None = None,
        confirmed: list[dict] | None = None,
    ) -> RoundOutcome:
        """Plan round r. `reuse` re-plans after a person answered the agent's questions (`confirmed`): the model is
        not asked again, the inbox and the anomalies are taken from the first attempt."""
        run = f"round-{r:02d}" if reuse is None else f"round-{r:02d}#2"
        at = settings.iso(settings.plan_date(r))
        drop = settings.iso(settings.drop_date(r))
        self._now, self._run = at, run
        cfg = settings.agent()
        usage = Usage()

        # 1. universe, scores, suppressions
        uni = self.warehouse.universe(at)
        response, value, version = self.models.scores(uni["company_id"], at)
        mask = rules.evaluate(uni)
        eligible0 = mask == 0
        scope_bits = sum(
            1 << i for i, rl in enumerate(settings.suppressions()) if rl["id"] in ("not_corporate", "not_active")
        )
        in_scope = (mask & scope_bits) == 0  # the population the model scores, whoever is mailable this round
        edges, vedge = optimise.cell_edges(response, value, eligible0)
        priors = learning.model_priors(response, value, optimise.assign_cells(response, value, edges, vedge), eligible0)

        # 2. results and learning, starting from what the existing models predict
        snap = self.results.snapshot(at)
        complete = len(snap["rows"]) / max(snap["expected_rows"], 1) >= cfg["anomaly"]["feed_completeness_min"]
        if self.mode.learner == "none":
            posts = {"cells": {}, "creatives": {}}
        elif complete:
            posts = learning.posteriors(snap["rows"], r, self.mode.learner, priors)
            self.memory.put("facts/posteriors", posts, provenance="results", run=run, at=at)
        else:
            posts = self.memory.get("facts/posteriors") or {"cells": priors, "creatives": {}}
            self.ledger.record(
                at=at,
                run=run,
                step="learn",
                actor="planner_code",
                kind="learning_skipped",
                decision={"rows": len(snap["rows"]), "expected": snap["expected_rows"]},
                reason="results feed incomplete; planning on the last complete posteriors",
            )
        self._priors = priors

        # 3. anomalies: code detects, the model triages, a person looks
        q_last = self.memory.get("facts/score_quantiles")
        found, evidence = anomalies.detect(
            feed=snap,
            score_now=response[in_scope],
            score_last=np.asarray(q_last) if q_last else None,
            current_round=r,
        )
        evidence["model_version"] = version
        evidence["model_version_last_round"] = self.memory.get("facts/model_version")
        if reuse is None:
            triaged = self.steps.run(run, "triage", lambda: self._triage(found, evidence, run))
        else:
            triaged = [dict(a) for a in reuse.anomalies]
        for t in triaged:
            usage = usage + Usage(**t.pop("_usage", {}))

        # 4. directions
        prev = settings.iso(settings.plan_date(r - 1)) if r > 1 else "2025-12-01"
        msgs = self.inbox.messages(prev, at)
        if reuse is None:
            dirs = self.steps.run(run, "directions", lambda: self._directions(msgs, form_directions, run, r))
        else:
            dirs = [dict(d) for d in reuse.directions] + [
                {**c, "applied": True, "why": "confirmed by a person", "source": "person"} for c in confirmed or []
            ]
            for c in confirmed or []:
                self.ledger.record(
                    at=at,
                    run=run,
                    step="directions",
                    actor=c.get("sender_role", "head_of_direct_acquisition"),
                    kind="direction_confirmed",
                    decision=c,
                    reason="a person answered the agent's question",
                )
        for d in dirs:
            usage = usage + Usage(**d.pop("_usage", {}))
        applied = [d for d in dirs if d.get("applied")]

        # 5. plan (code)
        budget = cfg["limits"]["default_budget"]
        excluded, min_shares, paused, overrides = [], {}, False, []
        for d in applied:
            if d["kind"] == "set_budget":
                budget = float(d["value"])
            elif d["kind"] == "exclude_sector":
                excluded.append(d["sector"])
            elif d["kind"] == "creative_min_share":
                min_shares[d["creative"]] = float(d["value"])
            elif d["kind"] == "pause_round":
                paused = True
            elif d["kind"] == "override_suppression":
                overrides.append(d.get("sector") or "all")
            elif d["kind"] == "set_volume":
                budget = float(d["value"]) * cfg["economics"]["cost_per_letter"]
        plan_mask = mask
        if overrides and not self.mode.guarded:
            # what an unguarded agent does when an email tells it the suppression list is "outdated"
            keep = {"not_corporate", "not_active", "existing_customer"}
            bits = sum(1 << i for i, rl in enumerate(settings.suppressions()) if rl["id"] in keep)
            plan_mask = mask & bits
        creatives = self.register.creatives(drop)
        approved = sorted(c.code for c in creatives if c.approved and (c.approved_until or "") >= drop)
        if not self.mode.guarded:
            approved = sorted({*approved, *min_shares})
        last_version = self.memory.get("facts/model_version")
        hshare = 0.0
        if self.mode.holdout:
            hshare = self.mode.holdout_share if self.mode.holdout_share is not None else cfg["limits"]["holdout_share"]
            if last_version and last_version != version:
                hshare = max(hshare, cfg["limits"]["new_model_holdout_share"])
        plan_dict = self.steps.run(
            run,
            "plan",
            lambda: self._plan(
                r,
                drop,
                uni,
                response,
                value,
                plan_mask,
                excluded,
                budget,
                hshare,
                posts,
                approved,
                min_shares,
                paused,
                version,
            ).model_dump(),
        )
        plan = Plan(**plan_dict)

        # 6. file and checks (code)
        f = mailfile.build(plan, uni, response, value, plan_mask, within_cell=self._within_cell())
        cap = cfg["limits"]["hard_budget_cap"]
        if any(d["kind"] == "set_budget" and d.get("sender_role") == "finance" for d in applied):
            cap = max(cap, budget)
        checks = mailfile.check(f, plan, uni, creatives, budget_cap=cap) if self.mode.guarded else []
        self.ledger.record(
            at=at,
            run=run,
            step="file",
            actor="planner_code",
            kind="file_built",
            decision={"sha256": f.sha256, "letters": f.letters, "holdout": int((f.arm == 0).sum())},
            reason=f"{sum(c.passed for c in checks)} of {len(checks)} checks passed" if checks else "unchecked",
            inputs=plan_dict,
        )

        # 7. brief (model writes, code checks every figure)
        last = self.memory.get(f"facts/rounds/{r - 1}")
        s = brief.stats(plan, checks, dirs, triaged, last)
        b = self.steps.run(run, "brief", lambda: self._brief(s))
        usage = usage + Usage(**b.pop("_usage", {}))

        # 8. ask the person
        approval_id = None
        if all(c.passed for c in checks):
            approval_id = self.approvals.request(
                run=run,
                kind="mail_file",
                artefact_sha=f.sha256,
                needs_role="head_of_direct_acquisition",
                requested_by="agent",
                expires_at=settings.iso(settings.print_date(r)),
                at=at,
            )
        else:
            self.tasks.open(
                run=run,
                owner_role="head_of_direct_acquisition",
                kind="file_failed_checks",
                payload={"failed": [c.model_dump() for c in checks if not c.passed]},
                dedupe=f"{run}:failed:{f.sha256}",
            )

        self.memory.put(
            f"facts/rounds/{r}",
            {"letters": plan.letters, "holdout": plan.holdout, "sha256": f.sha256, "model_version": version},
            provenance="results",
            run=run,
            at=at,
        )
        self.memory.put("facts/model_version", version, provenance="results", run=run, at=at)
        qs = np.quantile(response[in_scope], np.linspace(0, 1, 101)).tolist() if in_scope.any() else []
        self.memory.put("facts/score_quantiles", qs, provenance="results", run=run, at=at)
        if b.get("text"):
            self.toolbox.call(role="agent", run=run, name="memory.note", key=f"brief/{r}", text=b["text"])
        return RoundOutcome(
            round=r,
            plan=plan,
            file=f,
            checks=checks,
            brief=b.get("text"),
            brief_attempts=b.get("attempts", 0),
            brief_fallback=b.get("fallback", False),
            directions=dirs,
            anomalies=triaged,
            usage=usage,
            approval_id=approval_id,
            suppressed=rules.reasons(mask),
            eligible=int(eligible0.sum()),
            person_tasks=self.tasks.list(run=f"round-{r:02d}"),
        )

    def release(self, outcome: RoundOutcome) -> dict | None:
        """Send the approved file to the printer. Code holds this tool, and it checks the approval itself."""
        r = outcome.round
        at = settings.iso(settings.print_date(r))
        self._now = at
        if self.mode.guarded and not all(c.passed for c in outcome.checks):
            return None
        if not self.approvals.valid(kind="mail_file", artefact_sha=outcome.file.sha256, at=at):
            self.ledger.record(
                at=at,
                run=f"round-{r:02d}",
                step="release",
                actor="planner_code",
                kind="release_refused",
                decision={"sha256": outcome.file.sha256},
                reason="no valid approval for this exact file",
            )
            return None
        withdraw: list[int] = []
        if self.mode.guarded:
            # last suppression run on the print day: anyone who objected or became a customer since the plan
            f = outcome.file
            mailed = f.company_id[f.arm == 1]
            uni = self.warehouse.universe(at)
            ids = uni["company_id"]
            sorter = np.argsort(ids, kind="stable")
            rows = sorter[np.searchsorted(ids, mailed, sorter=sorter)]
            late = rules.evaluate({k: v[rows] for k, v in uni.items()})
            withdraw = mailed[late != 0].astype(int).tolist()
        return self.toolbox.call(
            role="planner_code",
            run=f"round-{r:02d}",
            name="printer.submit",
            idempotency_key=f"print:{outcome.file.sha256}",
            round=r,
            sha256=outcome.file.sha256,
            letters=outcome.file.letters,
            mail_codes=outcome.file.mail_codes(),
            withdraw=withdraw,
        )

    # -- steps ---------------------------------------------------------------------------------------------------
    def _within_cell(self) -> str:
        return "score" if self.mode.selection == "top_score" else "random"

    def _triage(self, found: list[dict], evidence: dict, run: str) -> list[dict]:
        owners = settings.permissions()["owners"]
        if not found:
            return []
        if self.reader is None:
            out = [{**a, "cause": None, "owner_role": "head_of_direct_acquisition", "diagnosed": False} for a in found]
        else:
            triage, u = self.reader.triage(found, evidence, owners)
            valid_roles = set(owners.values())
            out = []
            for a, t in zip(found, triage):
                role = t.owner_role if t.owner_role in valid_roles else "head_of_direct_acquisition"
                out.append({**a, "cause": t.cause, "owner_role": role, "explanation": t.explanation, "diagnosed": True})
            if out:
                out[0]["_usage"] = u.model_dump()
        for a in out:
            if a.get("cause") == "noise":
                continue
            self.tasks.open(
                run=run,
                owner_role=a["owner_role"],
                kind="anomaly",
                payload={k: v for k, v in a.items() if k != "_usage"},
                dedupe=f"{run.split('#')[0]}:anomaly:{a['anomaly']}",
            )
            self.ledger.record(
                at=self._now,
                run=run,
                step="triage",
                actor="agent" if self.reader else "planner_code",
                kind="anomaly_routed",
                decision={"anomaly": a["anomaly"], "cause": a.get("cause"), "owner": a["owner_role"]},
                reason=a.get("explanation") or "detected by code; not diagnosed",
                inputs=evidence,
            )
        return out

    def _directions(self, msgs: list[Message], form: list[dict] | None, run: str, r: int) -> list[dict]:
        by_id = {m.id: m for m in msgs}
        out: list[dict] = []
        if self.reader is None:
            for d in form or []:
                out.append({**d, "applied": True, "why": "entered by a person", "source": "form"})
            return out
        ctx = self.context(r)
        reading, u = self.reader.read_inbox(msgs, ctx)
        for d in reading.directives:
            m = by_id.get(d.message_id)
            if m is None:
                ok, why = False, "cites a message that does not exist"
            elif self.mode.guarded:
                ok, why = directives.validate(d, m)
            else:
                ok, why = True, "applied without checks"
            row = {
                **d.model_dump(),
                "sender": m.sender if m else "?",
                "sender_role": m.sender_role if m else "?",
                "applied": ok,
                "why": why,
                "source": "model",
            }
            out.append(row)
            self.ledger.record(
                at=self._now,
                run=run,
                step="directions",
                actor="agent",
                kind="direction_applied" if ok else "direction_not_applied",
                decision={k: row[k] for k in ("kind", "value", "sector", "creative", "sender")},
                reason=why,
                inputs=m.model_dump() if m else None,
            )
            if not ok:
                self.tasks.open(
                    run=run,
                    owner_role="head_of_direct_acquisition",
                    kind="confirm_direction",
                    payload={"message": d.message_id, "kind": d.kind, "why": why},
                    dedupe=f"{run.split('#')[0]}:confirm:{d.message_id}:{d.kind}",
                )
        for rt in reading.routes:
            self.tasks.open(
                run=run,
                owner_role=rt.owner_role,
                kind="routed",
                payload=rt.model_dump(),
                dedupe=f"{run.split('#')[0]}:route:{rt.message_id}",
            )
            out.append(
                {
                    "kind": "route",
                    "message_id": rt.message_id,
                    "owner_role": rt.owner_role,
                    "applied": False,
                    "why": rt.reason,
                    "source": "model",
                    "sender": by_id[rt.message_id].sender if rt.message_id in by_id else "?",
                }
            )
        # belt and braces: an objection must reach operations even if the model missed it
        routed_ids = {rt.message_id for rt in reading.routes if rt.owner_role == "operations"}
        for m in msgs:
            if m.id not in routed_ids and m.authenticated and objection.is_objection(m.body):
                self.tasks.open(
                    run=run,
                    owner_role="operations",
                    kind="routed",
                    payload={"message_id": m.id, "owner_role": "operations", "reason": "objection (rule)"},
                    dedupe=f"{run.split('#')[0]}:route:{m.id}",
                )
                out.append(
                    {
                        "kind": "route",
                        "message_id": m.id,
                        "owner_role": "operations",
                        "applied": False,
                        "why": "objection (rule)",
                        "source": "rule",
                        "sender": m.sender,
                    }
                )
        if out:
            out[0]["_usage"] = u.model_dump()
        else:
            out.append({"kind": "none", "applied": False, "why": "no directions", "_usage": u.model_dump()})
        return out

    def context(self, r: int) -> dict[str, Any]:
        """Everything the model is shown besides the messages: aggregates and settings, never a company."""
        cfg = settings.agent()
        drop = settings.iso(settings.drop_date(r))
        return {
            "round": r,
            "drop_date": drop,
            "default_budget": cfg["limits"]["default_budget"],
            "hard_budget_cap": cfg["limits"]["hard_budget_cap"],
            "sectors": sorted(cfg["sectors"]),
            "creatives": [{"code": c.code, "approved": c.approved} for c in self.register.creatives(drop)],
            "last_round": self.memory.get(f"facts/rounds/{r - 1}"),
        }

    def _plan(
        self,
        r,
        drop,
        uni,
        response,
        value,
        mask,
        excluded,
        budget,
        hshare,
        posts,
        approved,
        min_shares,
        paused,
        version,
    ) -> Plan:
        cfg = settings.agent()
        cost = cfg["economics"]["cost_per_letter"]
        rng = np.random.default_rng([self.seed, r])
        eligible = (mask == 0) & ~np.isin(uni["sector"], excluded)
        edges, vedge = optimise.cell_edges(response, value, mask == 0)
        codes = optimise.assign_cells(response, value, edges, vedge)
        names = {c: optimise.cell_name(c) for c in np.unique(codes)}
        available = {names[c]: int((eligible & (codes == c)).sum()) for c in names}
        cells_post = posts.get("cells", {})
        if paused:
            cells = [
                CellPlan(
                    cell=c, available=a, letters=0, holdout=0, value_per_letter=0.0, p_profitable=0.0, sampled_net=0.0
                )
                for c, a in sorted(available.items())
            ]
        elif self.mode.selection == "top_score":
            cap = int(min(budget / cost, cfg["limits"]["max_letters"]))
            idx = np.flatnonzero(eligible)
            top = idx[np.argsort(-response[idx], kind="stable")[:cap]]
            counts = {names[c]: int((codes[top] == c).sum()) for c in names}
            cells = [
                CellPlan(
                    cell=c,
                    available=available[c],
                    letters=counts[c],
                    holdout=0,
                    value_per_letter=round(learning.mean_value(cells_post[c]), 4) if c in cells_post else 0.0,
                    p_profitable=0.0,
                    sampled_net=0.0,
                )
                for c in sorted(available)
            ]
        else:
            cells = optimise.allocate(
                cells_post,
                available,
                budget=budget,
                holdout_share=hshare,
                rng=rng,
                priors=self._priors,
                explore_holdout=self.mode.learner == "incremental",
            )
        shares = optimise.creative_shares(posts.get("creatives", {}), approved, min_shares, rng)
        if self.mode.selection == "top_score":
            # today: one house letter, plus whatever share the Head of Direct Acquisition asks for
            house = cfg["round"]["house_creative"] if cfg["round"]["house_creative"] in approved else None
            shares = {house: 1.0} if house else {}
            for c, share in min_shares.items():
                if c in approved and c != house and house:
                    shares = {house: round(1 - share, 4), c: share}
        letters = sum(c.letters for c in cells)
        notes = []
        for c in min_shares:
            if c not in approved:
                notes.append(f"{c} is not approved by compliance for {drop}; it gets no letters")
        plan = Plan(
            round=r,
            drop_date=drop,
            budget=budget,
            letters=letters,
            holdout=sum(c.holdout for c in cells),
            cost=round(letters * cost, 2),
            holdout_share=hshare,
            cells=cells,
            creative_shares=shares,
            excluded_sectors=sorted(excluded),
            model_version=version,
            band_edges=edges,
            value_edge=vedge,
            expected_incremental_value=round(sum(c.letters * c.value_per_letter for c in cells), 2),
            paused=paused,
            notes=notes,
        )
        self.ledger.record(
            at=self._now,
            run=f"round-{r:02d}",
            step="plan",
            actor="planner_code",
            kind="plan",
            decision={"letters": plan.letters, "holdout": plan.holdout, "budget": budget, "cells": len(cells)},
            reason=(
                "paused by direction"
                if paused
                else f"{len(cells)} cells ranked by expected value per letter, holdout {hshare:.0%},"
                f" budget £{budget:,.0f}"
            ),
            inputs={"posts": posts.get("cells", {}), "available": available},
        )
        return plan

    def _brief(self, s: dict) -> dict:
        if self.reader is None:
            return {"text": None, "attempts": 0, "fallback": False}
        usage = Usage()
        for attempt in range(1, settings.agent()["brief"]["max_attempts"] + 1):
            text, u = self.reader.write_brief(s, attempt)
            usage = usage + u
            bad = brief.verify(text, s)
            if not bad:
                return {"text": text, "attempts": attempt, "fallback": False, "_usage": usage.model_dump()}
        return {"text": brief.template(s), "attempts": attempt, "fallback": True, "_usage": usage.model_dump()}


__all__ = ["Directive", "Mode", "RoundAgent", "RoundOutcome"]
