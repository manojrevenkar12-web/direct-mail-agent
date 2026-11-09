"""The approval brief: the model writes it for the person who approves; code checks every number in it.

A number in the brief that is not one of the plan's figures fails the check. After the configured attempts the
brief falls back to a template written by code, so the approver never reads an unchecked figure.
"""

from __future__ import annotations

import re

from mailagent import settings
from mailagent.schema import Check, Plan

FIG = re.compile(r"(?<![A-Za-z0-9-])£?\d[\d,]*(?:\.\d+)?(?:k|m|%)?(?![A-Za-z0-9])", re.IGNORECASE)


def stats(plan: Plan, checks: list[Check], directions: list[dict], anomalies: list[dict], last: dict | None) -> dict:
    """The only figures a brief may contain."""
    s = {
        "round": plan.round,
        "letters": plan.letters,
        "holdout": plan.holdout,
        "cost": round(plan.cost, 2),
        "budget": plan.budget,
        "holdout_share_pct": round(plan.holdout_share * 100, 1),
        "expected_incremental_value": round(plan.expected_incremental_value, 0),
        "cells_mailed": sum(1 for c in plan.cells if c.letters > 0),
        "checks_passed": sum(c.passed for c in checks),
        "checks_total": len(checks),
        "creative_shares_pct": {k: round(v * 100, 1) for k, v in plan.creative_shares.items()},
        "excluded_sectors": plan.excluded_sectors,
        "directions_applied": [_d(d) for d in directions if d.get("applied")],
        "directions_not_applied": [
            _d(d) for d in directions if not d.get("applied") and d.get("kind") not in ("none", "route")
        ],
        "anomalies": [{k: a.get(k) for k in ("anomaly", "cause", "owner_role") if a.get(k)} for a in anomalies],
        "drop_date": plan.drop_date,
    }
    if last:
        s["letters_last_round"] = last.get("letters", 0)
        s["change_in_letters"] = plan.letters - last.get("letters", 0)
    return s


def _d(d: dict) -> dict:
    return {k: d.get(k) for k in ("kind", "value", "sector", "creative", "sender", "why") if d.get(k) is not None}


def _allowed(s: dict) -> list[float]:
    vals: list[float] = []

    def walk(x):
        if isinstance(x, bool):
            return
        if isinstance(x, (int, float)):
            vals.extend([float(x), abs(float(x))])
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, str):
            for m in re.finditer(r"\d[\d,]*(?:\.\d+)?", x):
                vals.append(float(m.group().replace(",", "")))

    walk(s)
    return vals


def _parse(tok: str) -> list[float]:
    t = tok.lower().replace("£", "").replace(",", "")
    mult = 1.0
    if t.endswith("k"):
        mult, t = 1e3, t[:-1]
    elif t.endswith("m"):
        mult, t = 1e6, t[:-1]
    pct = t.endswith("%")
    t = t.rstrip("%")
    x = float(t) * mult
    return [x, x / 100] if pct else [x]


def verify(text: str, s: dict) -> list[str]:
    """Numbers in the text that are not plan figures (dates and the round's mail codes excluded)."""
    tol = settings.agent()["brief"]["number_tolerance"]
    allowed = _allowed(s)
    clean = re.sub(r"\d{4}-\d{2}-\d{2}", " ", text)
    clean = re.sub(r"\bR\d{2}-[A-Z0-9-]+", " ", clean)
    clean = re.sub(r"\bb\d+v\d+\b", " ", clean)
    bad = []
    for m in FIG.finditer(clean):
        cands = _parse(m.group())
        if not any(abs(c - a) <= max(tol * abs(a), 0.051) for c in cands for a in allowed):
            bad.append(m.group())
    return bad


def template(s: dict) -> str:
    lines = [
        f"Round {s['round']}, drop {s['drop_date']}: {s['letters']:,} letters and {s['holdout']:,} held out "
        f"({s['holdout_share_pct']}%), cost £{s['cost']:,.2f} of a £{s['budget']:,.0f} budget.",
        f"Expected incremental funded value £{s['expected_incremental_value']:,.0f}; {s['cells_mailed']} cells mailed.",
        f"Checks: {s['checks_passed']} of {s['checks_total']} passed.",
    ]
    if s["excluded_sectors"]:
        lines.append("Excluded sectors: " + ", ".join(s["excluded_sectors"]) + ".")
    for d in s["directions_not_applied"]:
        lines.append(f"Not applied: {d['kind']} from {d['sender']} ({d['why']}).")
    for a in s["anomalies"]:
        lines.append(f"Anomaly {a['anomaly']}: routed to {a.get('owner_role', 'a person')}.")
    return "\n".join(lines)
