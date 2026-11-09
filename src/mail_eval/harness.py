"""One policy, one market, twelve rounds.

The people in the loop are simulated too: the Head of Direct Acquisition approves a file whose checks all pass and
answers the agent's questions truthfully; customer service forwards objections; operations suppresses what reaches
it. Person-minutes come from config/costs.toml and are the same for every policy.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from agentrt.approvals import Person
from agentrt.store import connect
from mailagent import settings
from mailagent.agent import Mode, RoundAgent
from mailworld.adapters import World, ports
from mailworld.llm import SimulatedReader, true_cause
from mailworld.market import Market, day

POLICIES = {
    "today": Mode(name="today", selection="top_score", learner="none", reader=False, holdout=False),
    "for_loop": Mode(name="for_loop", reader=False),
    "agent": Mode(name="agent"),
    "agent_no_delay": Mode(name="agent_no_delay", learner="response_no_delay"),
    "agent_no_holdout": Mode(name="agent_no_holdout", holdout=False),
    "agent_cell_holdouts": Mode(name="agent_cell_holdouts", learner="incremental", holdout_share=0.10),
    "unguarded_llm": Mode(name="unguarded_llm", guarded=False),
}
HEAD = Person("sam.head", "head_of_direct_acquisition")


@dataclass
class RunResult:
    policy: str
    scenario: str
    seed: int
    rounds: list[dict]
    calibration: dict
    ledger_intact: bool
    printer_duplicates: int
    measurement: dict


def _effects(dirs: list[dict], mid: str) -> set[tuple]:
    out = set()
    for d in dirs:
        if d.get("message_id") == mid and d.get("applied") and d["kind"] not in ("route", "none"):
            v = d.get("value")
            out.add((d["kind"], round(float(v), 4) if v is not None else None, d.get("sector"), d.get("creative")))
    return out


def _truth_effects(t: dict) -> set[tuple]:
    return {
        (
            d["kind"],
            round(float(d["value"]), 4) if d.get("value") is not None else None,
            d.get("sector"),
            d.get("creative"),
        )
        for d in t["apply"]
    }


def run(policy: str, scenario: str = "dev", seed_offset: int = 0, size: int | None = None) -> RunResult:
    mode = POLICIES[policy]
    market = Market(scenario, size=size, seed_offset=seed_offset)
    world = World(market)
    conn = connect()
    events_by_round = {}
    for e in market.sc["events"]:
        events_by_round.setdefault(e["round"], set()).add(e["kind"])
    truth_msgs: dict[str, dict] = {}
    reader = None
    if mode.reader:
        reader = SimulatedReader(truth_msgs, set(), seed=market.sc["seed"] * 31 + seed_offset)
    agent = RoundAgent(conn, reader=reader, mode=mode, seed=market.sc["seed"] + seed_offset, **ports(world))
    people = settings.costs()["people_minutes"]
    price = settings.costs()["model"]
    rounds = []
    for r in range(1, market.sc["rounds"] + 1):
        msgs = world.inbox_for(r)
        for m, t in msgs:
            truth_msgs[m.id] = t
        if reader is not None:
            reader.events = events_by_round.get(r, set())
        form = []
        for m, t in msgs:
            for d in t["apply"]:
                form.append({**d, "message_id": m.id, "sender": m.sender, "sender_role": m.sender_role})
        out = agent.plan_round(r, form_directions=form if not mode.reader else None)
        first = out
        minutes = 0.0
        confirms = [t for t in out.person_tasks if t["kind"] == "confirm_direction"]
        if mode.reader and mode.guarded:
            # the Head of Direct Acquisition answers the agent's questions; re-plan once with the answers
            confirmed = []
            for task in confirms:
                mid = task["payload"]["message"]
                t = truth_msgs.get(mid, {"apply": []})
                if t["apply"] and _effects(out.directions, mid) != _truth_effects(t):
                    m = next(mm for mm, _ in msgs if mm.id == mid)
                    confirmed += [
                        {**d, "message_id": mid, "sender": m.sender, "sender_role": m.sender_role}
                        for d in t["apply"]
                        if (d["kind"],) not in {(c["kind"],) for c in confirmed}
                    ]
            minutes += people["confirm_direction"] * len(confirms)
            if confirmed:
                out = agent.plan_round(r, reuse=out, confirmed=confirmed)
        # direction handling, scored per message
        dir_scores = []
        for m, t in msgs:
            if not mode.reader:
                dir_scores.append({"kind": t["kind"], "correct": True})
                continue
            eff_ok = _effects(out.directions, m.id) == _truth_effects(t)
            first_ok = _effects(first.directions, m.id) == _truth_effects(t)
            model_raw = {
                (d["kind"], d.get("value"), d.get("sector"), d.get("creative"))
                for d in first.directions
                if d.get("message_id") == m.id and d.get("source") == "model" and d["kind"] not in ("route", "none")
            }
            raw_ok = model_raw == {(d["kind"], d.get("value"), d.get("sector"), d.get("creative")) for d in t["expect"]}
            routed = {
                task["owner_role"]
                for task in out.person_tasks
                if task["payload"].get("message") == m.id or task["payload"].get("message_id") == m.id
            }
            route_ok = t["route"] is None or t["route"] in routed
            stopped = sum(
                1
                for d in first.directions
                if d.get("message_id") == m.id
                and d.get("source") == "model"
                and not d.get("applied")
                and d["kind"] not in ("route", "none")
            )
            dir_scores.append(
                {
                    "kind": t["kind"],
                    "correct": bool(eff_ok and route_ok),
                    "effect_ok": eff_ok,
                    "route_ok": route_ok,
                    "first_pass_ok": first_ok,
                    "model_read_ok": raw_ok,
                    "stopped": stopped,
                }
            )
        # anomalies
        ev = events_by_round.get(r, set())
        anomaly_rows = []
        for a in out.anomalies:
            truth = true_cause(a["anomaly"], ev)
            row = {"anomaly": a["anomaly"], "truth": truth, "cause": a.get("cause"), "owner": a["owner_role"]}
            if a.get("diagnosed"):
                row["correct"] = a.get("cause") == truth
                if a.get("cause") != "noise":
                    ok = row["correct"]
                    minutes += people["investigate_with_diagnosis" if ok else "investigate_without_diagnosis"]
            else:
                row["correct"] = None
                minutes += people["investigate_without_diagnosis"]
            anomaly_rows.append(row)
        missed_events = sorted(
            e
            for e in ev
            if e in ("tracking_break", "feed_outage", "model_update", "competitor_offer")
            and not any(x["truth"] != "noise" and x["anomaly"] for x in anomaly_rows if _matches(x, e))
        )
        # approval and print
        approved = False
        if out.approval_id is not None:
            agent.approvals.decide(
                out.approval_id,
                person=HEAD,
                approve=True,
                at=settings.iso(settings.plan_date(r)),
                note="checks passed; brief read",
            )
            approved = True
        sub = agent.release(out) if approved and out.plan.letters > 0 else None
        if sub is not None and r == 1 and mode.name == "agent":
            agent.release(out)  # a retry after a timeout must not print twice
        withdraw = np.asarray(sub["withdraw"], dtype=np.int64) if sub else None
        truth = market.print_and_drop(r, out.file if sub else None, withdraw)
        # objections that reached operations
        plan_day = day(settings.iso(settings.plan_date(r)))
        for m, t in msgs:
            if t["kind"] != "objection":
                continue
            routed = not mode.reader or any(
                task["payload"].get("message_id") == m.id and task["owner_role"] == "operations"
                for task in out.person_tasks
            )
            if routed:
                market.route_objection(t["row"], plan_day)
        # person time
        actionable = sum(1 for _, t in msgs if t["apply"] or t["route"])
        if mode.name == "today":
            minutes += people["manual_file_build"] + people["approve_without_brief"]
            minutes += people["enter_direction_form"] * actionable
        elif not mode.reader:
            minutes += people["approve_without_brief"] + people["enter_direction_form"] * actionable
        else:
            minutes += people["approve_with_brief"]
            routed_q = [t for t in out.person_tasks if t["kind"] == "routed" and t["owner_role"] != "operations"]
            minutes += people["confirm_direction"] * len(routed_q)
        u = out.usage
        llm_gbp = (
            (
                u.input_tokens * price["input_per_mtok"]
                + u.output_tokens * price["output_per_mtok"]
                + u.cache_read_tokens * price["cache_read_per_mtok"]
            )
            / 1e6
            * price["usd_to_gbp"]
        )
        tasks = [t for t in out.person_tasks if t["kind"] != "routed" or t["owner_role"] != "operations"]
        rounds.append(
            {
                "round": r,
                "drop_date": out.plan.drop_date,
                "letters": truth["letters"],
                "holdout": out.plan.holdout if sub else 0,
                "spend": round(truth["spend"], 2),
                "budget": out.plan.budget,
                "exp_incremental_value": round(truth["exp_incremental_value"], 2),
                "realised_incremental_value": round(truth["mail_caused_value"], 2),
                "mail_caused_funded": truth["mail_caused_funded"],
                "attributed_funded": truth.get("attributed_funded", 0),
                "breaches": truth["breaches"],
                "withdrawn": len(sub["withdraw"]) if sub else 0,
                "checks_passed": all(c.passed for c in out.checks) if out.checks else None,
                "approved": approved,
                "paused": out.plan.paused,
                "excluded_sectors": out.plan.excluded_sectors,
                "creative_shares": out.plan.creative_shares,
                "directions": dir_scores,
                "anomalies": anomaly_rows,
                "missed_events": missed_events,
                "person_tasks": len(tasks),
                "person_minutes": minutes,
                "llm_tokens_in": u.input_tokens + u.cache_read_tokens,
                "llm_tokens_out": u.output_tokens,
                "llm_gbp": round(llm_gbp, 4),
                "brief_attempts": out.brief_attempts,
                "brief_fallback": out.brief_fallback,
                "eligible": out.eligible,
                "plan_cells": [c.model_dump() for c in out.plan.cells],
            }
        )
    calib = _calibration(agent, market) if mode.learner == "incremental" else {}
    measured = _measurement(market) if mode.holdout else {}
    ok, _ = agent.ledger.verify()
    shas = [s["sha256"] for s in world.submissions]
    return RunResult(policy, scenario, seed_offset, rounds, calib, ok, len(shas) - len(set(shas)), measured)


def _measurement(market: Market) -> dict:
    """What mail was worth, three ways, over the complete rounds: the truth, the holdout estimate, matchback."""
    last = max(market.files)
    as_of = settings.iso(settings.drop_date(last) + __import__("datetime").timedelta(days=61))
    rows = market.snapshot(as_of, lookback_days=10_000)["rows"]
    est, attributed = 0.0, 0
    cells: dict[tuple[int, str], list[int]] = {}
    for x in rows:
        c = cells.setdefault((x["round"], x["cell"]), [0, 0, 0, 0])
        i = 0 if x["arm"] == "mail" else 2
        c[i] += x["n"]
        c[i + 1] += x["apps"]
    for n_m, a_m, n_h, a_h in cells.values():
        attributed += a_m
        if n_m and n_h:
            est += a_m - n_m * a_h / n_h  # the mailed arm against its own random holdout
    truth = sum(inc for cells in market.cell_inc.values() for inc, _ in cells.values())
    return {
        "true_incremental_apps": truth,
        "holdout_estimate": est,
        "matchback_apps": attributed,
        "holdout_ratio": est / truth if truth else None,
        "matchback_ratio": attributed / truth if truth else None,
    }


def _matches(row: dict, event: str) -> bool:
    return {
        "tracking_break": "tracking_break",
        "feed_outage": "feed_incomplete",
        "model_update": "model_shift",
        "competitor_offer": "response_drop",
    }[event] == row["truth"]


def _calibration(agent: RoundAgent, market: Market) -> dict:
    """Do the learner's 90% intervals for each cell's incremental rate contain the truth, in the last round?"""
    posts = (agent.memory.get("facts/posteriors") or {}).get("cells", {})
    last = max(market.files)
    truth = market.cell_truth(last, settings.agent()["learning"]["half_life_rounds"])
    rng = np.random.default_rng(0)
    rows = []
    for cell, t in truth.items():
        p = posts.get(cell)
        if not p:
            continue
        lift = rng.beta(*p["mail"], 20000) - rng.beta(*p["holdout"], 20000)
        lo, hi = np.quantile(lift, [0.05, 0.95])
        rows.append(
            {
                "cell": cell,
                "truth": t,
                "mean": float(lift.mean()),
                "lo": float(lo),
                "hi": float(hi),
                "covered": bool(lo <= t <= hi),
            }
        )
    return {"cells": rows, "coverage": float(np.mean([r["covered"] for r in rows])) if rows else None}
